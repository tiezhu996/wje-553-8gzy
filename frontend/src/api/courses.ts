import { request } from '../utils/request';
import type { Course, CoursePayload } from '../types/course';
import type { Enrollment, EnrollResult } from '../types/enrollment';
export const courseApi = {
  list: (params?: Record<string, string>) => request.get<unknown, Course[]>('/courses', { params }),
  get: (id: string) => request.get<unknown, Course>('/courses/' + id),
  create: (payload: CoursePayload) => request.post<unknown, Course>('/courses', payload),
  update: (id: string, payload: Partial<CoursePayload>) => request.patch<unknown, Course>('/courses/' + id, payload),
  enrollments: (courseId: string) => request.get<unknown, Enrollment[]>('/courses/' + courseId + '/enrollments'),
  enroll: (courseId: string, studentId: string) => request.post<unknown, EnrollResult>('/courses/' + courseId + '/enroll/' + studentId),
  drop: (courseId: string, studentId: string) => request.delete<unknown, { message: string }>('/courses/' + courseId + '/enroll/' + studentId),
};
