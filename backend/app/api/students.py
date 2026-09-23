from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.enums import EnrollmentStatus
from app.models.student import Student
from app.schemas.course_schema import EnrollmentRead
from app.schemas.student_schema import StudentCreate, StudentRead, StudentUpdate
from app.services.course_service import course_service
from app.services.student_service import student_service

router = APIRouter(prefix="/students", tags=["students"])

@router.get("/me", response_model=StudentRead)
def get_my_student_profile(request: Request, db: Session = Depends(get_db)):
    """根据登录用户返回其学生档案。"""
    student = db.query(Student).filter(Student.user_id == request.state.user["id"]).first()
    if not student:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="当前账号未关联学生档案")
    return student

@router.get("/me/enrollments", response_model=list[EnrollmentRead])
def get_my_enrollments(request: Request, db: Session = Depends(get_db)):
    """已选课程 + 候补队列，供学生“我的课程”使用。"""
    student = db.query(Student).filter(Student.user_id == request.state.user["id"]).first()
    if not student:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="当前账号未关联学生档案")
    return list_student_enrollments(str(student.id), db)

@router.get("", response_model=list[StudentRead])
def list_students(db: Session = Depends(get_db)):
    return student_service.list_students(db)

@router.post("", response_model=StudentRead)
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    return student_service.create_student(db, payload)

@router.get("/{student_id}/enrollments", response_model=list[EnrollmentRead])
def list_student_enrollments(student_id: str, db: Session = Depends(get_db)):
    items = course_service.list_student_enrollments(db, student_id)
    result = []
    for item in items:
        enrolled = sum(1 for e in item.course.enrollments if e.status == EnrollmentStatus.ENROLLED)
        waitlisted = sum(1 for e in item.course.enrollments if e.status == EnrollmentStatus.WAITLISTED)
        queue_position = None
        if item.status == EnrollmentStatus.WAITLISTED:
            queue_position = course_service._queue_position(db, item.course_id, item.waitlist_position)
        result.append(EnrollmentRead(
            id=item.id, course_id=item.course_id, student_id=item.student_id,
            status=item.status, waitlist_position=queue_position, created_at=item.created_at,
            course_name=item.course.name, course_code=item.course.code,
            semester=item.course.semester, max_students=item.course.max_students,
            enrolled_count=enrolled, waitlist_count=waitlisted,
        ))
    return result

@router.patch("/{student_id}", response_model=StudentRead)
def update_student(student_id: str, payload: StudentUpdate, db: Session = Depends(get_db)):
    return student_service.update_student(db, student_id, payload)
