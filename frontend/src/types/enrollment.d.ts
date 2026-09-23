import type { EnrollmentStatus } from '../constants/enums';

export interface Enrollment {
  id: string;
  course_id: string;
  student_id: string;
  status: EnrollmentStatus;
  /** 候补排队位置（仅候补时有值，从 1 开始） */
  waitlist_position?: number | null;
  created_at: string;
  course_name?: string;
  course_code?: string;
  semester?: string;
  max_students?: number;
  enrolled_count?: number;
  waitlist_count?: number;
}

export interface EnrollResult {
  status: EnrollmentStatus;
  message: string;
  waitlist_position?: number | null;
  course_id: string;
  student_id: string;
}
