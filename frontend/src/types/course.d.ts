import type { CourseStatus, EnrollmentStatus } from '../constants/enums';
export interface Course { id: string; name: string; code: string; teacher_id: string; teacher_name?: string; description?: string; max_students: number; semester?: string; status: CourseStatus; enrolled_count: number; waitlisted_count: number; my_status?: EnrollmentStatus | null; my_position?: number | null; created_at: string; updated_at: string }
export type CoursePayload = Omit<Course, 'id'|'teacher_name'|'enrolled_count'|'waitlisted_count'|'my_status'|'my_position'|'created_at'|'updated_at'>;
export interface EnrollmentResult { message: string; status: EnrollmentStatus; position?: number | null }
