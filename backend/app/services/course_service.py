import threading
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.enums import CourseStatus, EnrollmentStatus
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.student import Student
from app.schemas.course_schema import CourseCreate, CourseUpdate
from .audit_service import audit_service

# 每门课一把进程内互斥锁：SQLite 没有真正的行锁，依靠它串行化
# “查空位 -> 入选 / 入候补”与“退课 -> 补位”的临界区；
# PostgreSQL 侧再叠加 SELECT ... FOR UPDATE 行锁，防止多进程/多实例并发抢位。
_course_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

def _course_lock(course_id: str) -> threading.Lock:
    with _locks_guard:
        lock = _course_locks.get(course_id)
        if lock is None:
            lock = threading.Lock()
            _course_locks[course_id] = lock
        return lock


class CourseService:
    def list_courses(self, db: Session, keyword: str | None = None, status: CourseStatus | None = None, semester: str | None = None):
        query = db.query(Course)
        if keyword:
            query = query.filter(Course.name.ilike(f"%{keyword}%") | Course.code.ilike(f"%{keyword}%"))
        if status:
            query = query.filter(Course.status == status)
        if semester:
            query = query.filter(Course.semester == semester)
        return query.order_by(Course.created_at.desc()).all()

    def get_course(self, db: Session, course_id: str) -> Course:
        course = db.get(Course, course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        return course

    def create_course(self, db: Session, payload: CourseCreate, user_id=None) -> Course:
        course = Course(**payload.model_dump())
        db.add(course)
        db.commit(); db.refresh(course)
        audit_service.log(db, "course.create", "Course", str(course.id), user_id=user_id, after_data={"code": course.code, "status": course.status.value})
        return course

    def update_course(self, db: Session, course_id: str, payload: CourseUpdate, user_id=None) -> Course:
        data = payload.model_dump(exclude_unset=True)
        lock = _course_lock(str(course_id))
        with lock:
            # PostgreSQL：锁住课程行，容量调整与选课/退课/补位互斥
            course = db.query(Course).filter(Course.id == course_id).with_for_update().first()
            if not course:
                raise HTTPException(status_code=404, detail="Course not found")
            before = {"status": course.status.value, "name": course.name, "max_students": course.max_students}

            new_capacity = data.get("max_students")
            if new_capacity is not None:
                enrolled = self._enrolled_query(db, course_id).count()
                if new_capacity < 1:
                    raise HTTPException(status_code=400, detail="课程容量必须大于 0")
                if new_capacity < enrolled:
                    # 容量不能低于已入选人数；明确告知还差多少人
                    overflow = enrolled - new_capacity
                    raise HTTPException(
                        status_code=400,
                        detail=f"容量不能低于已入选人数：当前已入选 {enrolled} 人，目标容量 {new_capacity} 人，还需减少 {overflow} 人（容量至少为 {enrolled}）",
                    )

            for key, value in data.items():
                setattr(course, key, value)

            promotions = []
            # 调高容量释放出新名额时，按候补顺序自动补位
            if new_capacity is not None and new_capacity > before["max_students"]:
                promotions = self._promote_waitlist(db, course)

            audit_service.log(db, "course.update", "Course", str(course.id), user_id=user_id, before_data=before, after_data={**data, "auto_promoted": len(promotions)}, commit=False)
            db.commit(); db.refresh(course)
            return course

    # ----- 选课 / 候补 -----

    def enroll(self, db: Session, course_id: str, student_id: str, user_id=None) -> dict:
        lock = _course_lock(str(course_id))
        with lock:
            # 注意：必须先拿进程内锁再开启写事务，避免持有数据库写锁后互相等待
            if not db.get(Student, student_id):
                raise HTTPException(status_code=404, detail="Student not found")

            course = db.query(Course).filter(Course.id == course_id).with_for_update().first()
            if not course:
                raise HTTPException(status_code=404, detail="Course not found")

            existing = db.query(Enrollment).filter_by(course_id=course_id, student_id=student_id).first()
            if existing:
                if existing.status == EnrollmentStatus.ENROLLED:
                    raise HTTPException(status_code=400, detail="Already enrolled")
                position = self._queue_position(db, course_id, existing.waitlist_position)
                raise HTTPException(status_code=400, detail=f"已在候补队列中，当前排队位置：第 {position} 位")

            enrolled_count = self._enrolled_query(db, course_id).count()
            if enrolled_count < course.max_students:
                # 有空位：直接入选
                item = Enrollment(course_id=course_id, student_id=student_id, status=EnrollmentStatus.ENROLLED, waitlist_position=None)
                db.add(item)
                audit_service.log(db, "enrollment.create", "Course", course_id, user_id=user_id, after_data={"student_id": student_id, "status": EnrollmentStatus.ENROLLED.value}, commit=False)
                db.commit(); db.refresh(item)
                return {"status": EnrollmentStatus.ENROLLED, "message": "选课成功", "waitlist_position": None, "course_id": course_id, "student_id": student_id}

            # 满额：进入候补，按提交顺序排队
            position_value = self._next_waitlist_value(db, course_id)
            item = Enrollment(course_id=course_id, student_id=student_id, status=EnrollmentStatus.WAITLISTED, waitlist_position=position_value)
            db.add(item); db.flush()
            queue_position = self._queue_position(db, course_id, position_value)
            audit_service.log(db, "enrollment.waitlist", "Course", course_id, user_id=user_id, after_data={"student_id": student_id, "status": EnrollmentStatus.WAITLISTED.value, "position": queue_position}, commit=False)
            db.commit()
            return {"status": EnrollmentStatus.WAITLISTED, "message": f"课程已满，已进入候补队列，当前排队位置：第 {queue_position} 位", "waitlist_position": queue_position, "course_id": course_id, "student_id": student_id}

    def drop(self, db: Session, course_id: str, student_id: str, user_id=None) -> dict:
        """退课或退出候补：入选学生退课后自动补位队首；候补学生直接离队。"""
        lock = _course_lock(str(course_id))
        with lock:
            course = db.query(Course).filter(Course.id == course_id).with_for_update().first()
            if not course:
                raise HTTPException(status_code=404, detail="Course not found")

            item = db.query(Enrollment).filter_by(course_id=course_id, student_id=student_id).first()
            if not item:
                raise HTTPException(status_code=404, detail="Enrollment not found")

            was_waitlisted = item.status == EnrollmentStatus.WAITLISTED
            old_position = self._queue_position(db, course_id, item.waitlist_position) if was_waitlisted else None
            db.delete(item)
            db.flush()

            promoted = None
            if not was_waitlisted:
                # 有人退课：等待最久且仍在候补的学生自动补位，并发选课无法抢走该名额
                promoted = self._promote_head(db, course)

            if was_waitlisted:
                audit_service.log(db, "enrollment.waitlist_leave", "Course", course_id, user_id=user_id, before_data={"student_id": student_id, "position": old_position}, commit=False)
                message = "已退出候补队列"
            else:
                audit_service.log(db, "enrollment.delete", "Course", course_id, user_id=user_id, before_data={"student_id": student_id, "promoted_student_id": str(promoted.student_id) if promoted else None}, commit=False)
                message = "已退课"
            db.commit()
            return {"message": message, "promoted_student_id": str(promoted.student_id) if promoted else None}

    # ----- 查询 -----

    def list_enrollments(self, db: Session, course_id: str, status: EnrollmentStatus | None = None) -> list[Enrollment]:
        self.get_course(db, course_id)
        query = db.query(Enrollment).filter_by(course_id=course_id)
        if status:
            query = query.filter(Enrollment.status == status)
        return query.order_by(Enrollment.created_at.asc()).all()

    def list_student_enrollments(self, db: Session, student_id: str) -> list[Enrollment]:
        if not db.get(Student, student_id):
            raise HTTPException(status_code=404, detail="Student not found")
        return db.query(Enrollment).filter_by(student_id=student_id).order_by(Enrollment.created_at.desc()).all()

    # ----- 内部辅助（调用方必须已持有课程锁/行锁）-----

    def _enrolled_query(self, db: Session, course_id: str):
        return db.query(Enrollment).filter_by(course_id=course_id, status=EnrollmentStatus.ENROLLED)

    def _waitlist_query(self, db: Session, course_id: str):
        return db.query(Enrollment).filter_by(course_id=course_id, status=EnrollmentStatus.WAITLISTED)

    def _next_waitlist_value(self, db: Session, course_id: str) -> int:
        # 单调递增的排队序号；离队/补位不复用，保证提交顺序严格可比
        current = db.query(func.max(Enrollment.waitlist_position)).filter_by(course_id=course_id).scalar()
        return (current or 0) + 1

    def _queue_position(self, db: Session, course_id: str, waitlist_value: int | None) -> int:
        """对外展示的排队位置 = 当前仍在候补且序号更早的人数 + 1。"""
        if waitlist_value is None:
            return 0
        return self._waitlist_query(db, course_id).filter(Enrollment.waitlist_position < waitlist_value).count() + 1

    def _promote_head(self, db: Session, course: Course) -> Enrollment | None:
        """空位补位：队首（等待最久）候补学生入选。"""
        enrolled_count = self._enrolled_query(db, course.id).count()
        if enrolled_count >= course.max_students:
            return None
        head = self._waitlist_query(db, course.id).order_by(Enrollment.waitlist_position.asc(), Enrollment.created_at.asc()).first()
        if not head:
            return None
        head.status = EnrollmentStatus.ENROLLED
        head.waitlist_position = None
        db.flush()
        audit_service.log(db, "enrollment.promote", "Course", str(course.id), after_data={"student_id": str(head.student_id)}, commit=False)
        return head

    def _promote_waitlist(self, db: Session, course: Course) -> list[Enrollment]:
        """容量调高后，按顺序尽可能多地补位。"""
        promoted = []
        while True:
            item = self._promote_head(db, course)
            if item is None:
                break
            promoted.append(item)
        return promoted


course_service = CourseService()
