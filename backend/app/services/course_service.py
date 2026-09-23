from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.enums import CourseStatus, EnrollmentStatus
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.student import Student
from app.schemas.course_schema import CourseCreate, CourseUpdate
from .audit_service import audit_service

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

    def _lock_course(self, db: Session, course_id: str) -> Course:
        # 行级锁串行化同一课程的选课/退课/调容，保证候补补位名额不会被并发请求抢走
        course = db.query(Course).filter(Course.id == course_id).with_for_update().first()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        return course

    def _enrolled_count(self, db: Session, course_id) -> int:
        return db.query(Enrollment).filter_by(course_id=course_id, status=EnrollmentStatus.ENROLLED).count()

    def _waitlist_position(self, db: Session, item: Enrollment) -> int:
        earlier = (
            db.query(Enrollment)
            .filter(
                Enrollment.course_id == item.course_id,
                Enrollment.status == EnrollmentStatus.WAITLISTED,
                Enrollment.created_at < item.created_at,
            )
            .count()
        )
        return earlier + 1

    def _promote_waitlist(self, db: Session, course: Course, user_id=None) -> None:
        # 有空位时按等待时长（提交顺序）把最早的候补学生补位为已入选
        while self._enrolled_count(db, course.id) < course.max_students:
            next_item = (
                db.query(Enrollment)
                .filter_by(course_id=course.id, status=EnrollmentStatus.WAITLISTED)
                .order_by(Enrollment.created_at.asc())
                .first()
            )
            if not next_item:
                break
            next_item.status = EnrollmentStatus.ENROLLED
            db.flush()
            audit_service.log(db, "enrollment.promote", "Course", str(course.id), user_id=user_id,
                              before_data={"student_id": str(next_item.student_id), "status": EnrollmentStatus.WAITLISTED.value},
                              after_data={"student_id": str(next_item.student_id), "status": EnrollmentStatus.ENROLLED.value},
                              commit=False)

    def create_course(self, db: Session, payload: CourseCreate, user_id=None) -> Course:
        course = Course(**payload.model_dump())
        db.add(course)
        db.commit(); db.refresh(course)
        audit_service.log(db, "course.create", "Course", str(course.id), user_id=user_id, after_data={"code": course.code, "status": course.status.value})
        return course

    def update_course(self, db: Session, course_id: str, payload: CourseUpdate, user_id=None) -> Course:
        course = self._lock_course(db, course_id)
        data = payload.model_dump(exclude_unset=True)
        if "max_students" in data and data["max_students"] is not None:
            enrolled = self._enrolled_count(db, course.id)
            if data["max_students"] < enrolled:
                raise HTTPException(status_code=400, detail=f"容量不能调低到少于已入选人数：当前已入选 {enrolled} 人，还差 {enrolled - data['max_students']} 人")
        before = {"status": course.status.value, "name": course.name, "max_students": course.max_students}
        for key, value in data.items():
            setattr(course, key, value)
        db.flush()
        self._promote_waitlist(db, course, user_id=user_id)
        db.commit(); db.refresh(course)
        audit_service.log(db, "course.update", "Course", str(course.id), user_id=user_id, before_data=before, after_data=payload.model_dump(exclude_unset=True, mode="json"))
        return course

    def enroll(self, db: Session, course_id: str, student_id: str, user_id=None) -> tuple[Enrollment, int | None]:
        course = self._lock_course(db, course_id)
        if not db.get(Student, student_id):
            raise HTTPException(status_code=404, detail="Student not found")
        existing = db.query(Enrollment).filter_by(course_id=course_id, student_id=student_id).first()
        if existing:
            if existing.status == EnrollmentStatus.ENROLLED:
                raise HTTPException(status_code=400, detail="Already enrolled")
            return existing, self._waitlist_position(db, existing)
        if self._enrolled_count(db, course.id) < course.max_students:
            item = Enrollment(course_id=course_id, student_id=student_id, status=EnrollmentStatus.ENROLLED)
            db.add(item); db.commit(); db.refresh(item)
            audit_service.log(db, "enrollment.create", "Course", course_id, user_id=user_id, after_data={"student_id": student_id, "status": EnrollmentStatus.ENROLLED.value})
            return item, None
        item = Enrollment(course_id=course_id, student_id=student_id, status=EnrollmentStatus.WAITLISTED)
        db.add(item); db.flush(); db.refresh(item)
        position = self._waitlist_position(db, item)
        db.commit()
        audit_service.log(db, "enrollment.waitlist", "Course", course_id, user_id=user_id, after_data={"student_id": student_id, "status": EnrollmentStatus.WAITLISTED.value, "position": position})
        return item, position

    def drop(self, db: Session, course_id: str, student_id: str, user_id=None) -> None:
        course = self._lock_course(db, course_id)
        item = db.query(Enrollment).filter_by(course_id=course_id, student_id=student_id, status=EnrollmentStatus.ENROLLED).first()
        if not item:
            raise HTTPException(status_code=404, detail="Enrollment not found")
        db.delete(item); db.flush()
        # 同一事务、持有课程行锁期间补位，并发选课请求会被锁阻塞，抢不走该名额
        self._promote_waitlist(db, course, user_id=user_id)
        db.commit()
        audit_service.log(db, "enrollment.delete", "Course", course_id, user_id=user_id, before_data={"student_id": student_id})

    def cancel_waitlist(self, db: Session, course_id: str, student_id: str, user_id=None) -> None:
        item = db.query(Enrollment).filter_by(course_id=course_id, student_id=student_id, status=EnrollmentStatus.WAITLISTED).first()
        if not item:
            raise HTTPException(status_code=404, detail="Waitlist entry not found")
        db.delete(item); db.commit()
        audit_service.log(db, "enrollment.waitlist_cancel", "Course", course_id, user_id=user_id, before_data={"student_id": student_id})

course_service = CourseService()
