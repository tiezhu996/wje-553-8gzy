from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.enums import CourseStatus, EnrollmentStatus, UserRole
from app.models.student import Student
from app.schemas.common_schema import Message
from app.schemas.course_schema import CourseCreate, CourseRead, CourseUpdate, EnrollmentResult
from app.services.course_service import course_service

router = APIRouter(prefix="/courses", tags=["courses"])

def current_student_id(db: Session, request: Request) -> str | None:
    user = getattr(request.state, "user", None)
    if not user or user.get("role") != UserRole.STUDENT.value:
        return None
    student = db.query(Student).filter(Student.user_id == user["id"]).first()
    return str(student.id) if student else None

def serialize(course, student_id: str | None = None):
    enrolled = [e for e in course.enrollments if e.status == EnrollmentStatus.ENROLLED]
    waitlisted = sorted((e for e in course.enrollments if e.status == EnrollmentStatus.WAITLISTED), key=lambda e: e.created_at)
    my_status, my_position = None, None
    if student_id:
        mine = next((e for e in course.enrollments if str(e.student_id) == student_id), None)
        if mine:
            my_status = mine.status
            if mine.status == EnrollmentStatus.WAITLISTED:
                my_position = [str(e.student_id) for e in waitlisted].index(student_id) + 1
    return CourseRead(
        id=str(course.id), name=course.name, code=course.code, teacher_id=str(course.teacher_id),
        teacher_name=course.teacher.full_name if course.teacher else None,
        description=course.description, max_students=course.max_students, semester=course.semester,
        status=course.status, enrolled_count=len(enrolled), waitlisted_count=len(waitlisted),
        my_status=my_status, my_position=my_position,
        created_at=course.created_at, updated_at=course.updated_at,
    )

@router.get("", response_model=list[CourseRead])
def list_courses(request: Request, keyword: str | None = None, status: CourseStatus | None = None, semester: str | None = None, db: Session = Depends(get_db)):
    student_id = current_student_id(db, request)
    return [serialize(c, student_id) for c in course_service.list_courses(db, keyword, status, semester)]

@router.post("", response_model=CourseRead)
def create_course(payload: CourseCreate, request: Request, db: Session = Depends(get_db)):
    return serialize(course_service.create_course(db, payload, request.state.user["id"]))

@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: str, request: Request, db: Session = Depends(get_db)):
    return serialize(course_service.get_course(db, course_id), current_student_id(db, request))

@router.patch("/{course_id}", response_model=CourseRead)
def update_course(course_id: str, payload: CourseUpdate, request: Request, db: Session = Depends(get_db)):
    return serialize(course_service.update_course(db, course_id, payload, request.state.user["id"]))

@router.post("/{course_id}/enroll/{student_id}", response_model=EnrollmentResult)
def enroll(course_id: str, student_id: str, request: Request, db: Session = Depends(get_db)):
    item, position = course_service.enroll(db, course_id, student_id, request.state.user["id"])
    if item.status == EnrollmentStatus.WAITLISTED:
        return EnrollmentResult(message="waitlisted", status=item.status, position=position)
    return EnrollmentResult(message="enrolled", status=item.status)

@router.delete("/{course_id}/enroll/{student_id}", response_model=Message)
def drop(course_id: str, student_id: str, request: Request, db: Session = Depends(get_db)):
    course_service.drop(db, course_id, student_id, request.state.user["id"])
    return {"message": "dropped"}

@router.delete("/{course_id}/waitlist/{student_id}", response_model=Message)
def cancel_waitlist(course_id: str, student_id: str, request: Request, db: Session = Depends(get_db)):
    course_service.cancel_waitlist(db, course_id, student_id, request.state.user["id"])
    return {"message": "waitlist cancelled"}
