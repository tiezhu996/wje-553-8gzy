from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.enums import CourseStatus, EnrollmentStatus
from app.schemas.common_schema import Message
from app.schemas.course_schema import CourseCreate, CourseRead, CourseUpdate, EnrollmentRead, EnrollmentResult
from app.services.course_service import course_service

router = APIRouter(prefix="/courses", tags=["courses"])

def _counts(course):
    enrolled = sum(1 for e in course.enrollments if e.status == EnrollmentStatus.ENROLLED)
    waitlisted = sum(1 for e in course.enrollments if e.status == EnrollmentStatus.WAITLISTED)
    return enrolled, waitlisted

def serialize(course):
    enrolled, waitlisted = _counts(course)
    return CourseRead(
        id=str(course.id), name=course.name, code=course.code, teacher_id=str(course.teacher_id),
        teacher_name=course.teacher.full_name if course.teacher else None,
        description=course.description, max_students=course.max_students, semester=course.semester,
        status=course.status, enrolled_count=enrolled, waitlist_count=waitlisted,
        created_at=course.created_at, updated_at=course.updated_at,
    )

@router.get("", response_model=list[CourseRead])
def list_courses(keyword: str | None = None, status: CourseStatus | None = None, semester: str | None = None, db: Session = Depends(get_db)):
    return [serialize(c) for c in course_service.list_courses(db, keyword, status, semester)]

@router.post("", response_model=CourseRead)
def create_course(payload: CourseCreate, request: Request, db: Session = Depends(get_db)):
    return serialize(course_service.create_course(db, payload, request.state.user["id"]))

@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: str, db: Session = Depends(get_db)):
    return serialize(course_service.get_course(db, course_id))

@router.patch("/{course_id}", response_model=CourseRead)
def update_course(course_id: str, payload: CourseUpdate, request: Request, db: Session = Depends(get_db)):
    return serialize(course_service.update_course(db, course_id, payload, request.state.user["id"]))

@router.get("/{course_id}/enrollments", response_model=list[EnrollmentRead])
def list_enrollments(course_id: str, status: EnrollmentStatus | None = None, db: Session = Depends(get_db)):
    items = course_service.list_enrollments(db, course_id, status)
    result = []
    for item in items:
        enrolled, waitlisted = _counts(item.course)
        queue_position = None
        if item.status == EnrollmentStatus.WAITLISTED:
            queue_position = course_service._queue_position(db, course_id, item.waitlist_position)
        result.append(EnrollmentRead(
            id=item.id, course_id=item.course_id, student_id=item.student_id,
            status=item.status, waitlist_position=queue_position, created_at=item.created_at,
            course_name=item.course.name, course_code=item.course.code,
            semester=item.course.semester, max_students=item.course.max_students,
            enrolled_count=enrolled, waitlist_count=waitlisted,
        ))
    return result

@router.post("/{course_id}/enroll/{student_id}", response_model=EnrollmentResult)
def enroll(course_id: str, student_id: str, request: Request, db: Session = Depends(get_db)):
    return course_service.enroll(db, course_id, student_id, request.state.user["id"])

@router.delete("/{course_id}/enroll/{student_id}", response_model=Message)
def drop(course_id: str, student_id: str, request: Request, db: Session = Depends(get_db)):
    result = course_service.drop(db, course_id, student_id, request.state.user["id"])
    return {"message": result["message"]}
