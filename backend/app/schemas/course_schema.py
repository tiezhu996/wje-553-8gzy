from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from app.core.enums import CourseStatus, EnrollmentStatus

class CourseBase(BaseModel):
    name: str
    code: str
    teacher_id: UUID
    description: str | None = None
    max_students: int = 60
    semester: str | None = None
    status: CourseStatus = CourseStatus.DRAFT

class CourseCreate(CourseBase):
    pass

class CourseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    max_students: int | None = None
    semester: str | None = None
    status: CourseStatus | None = None

class CourseRead(CourseBase):
    id: UUID
    teacher_name: str | None = None
    enrolled_count: int = 0
    waitlist_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class EnrollmentResult(BaseModel):
    """选课结果：直接入选或进入候补队列。"""
    status: EnrollmentStatus
    message: str
    waitlist_position: int | None = None
    course_id: UUID
    student_id: UUID

class EnrollmentRead(BaseModel):
    id: UUID
    course_id: UUID
    student_id: UUID
    status: EnrollmentStatus
    waitlist_position: int | None = None
    created_at: datetime
    course_name: str | None = None
    course_code: str | None = None
    semester: str | None = None
    max_students: int | None = None
    enrolled_count: int | None = None
    waitlist_count: int | None = None

    class Config:
        from_attributes = True
