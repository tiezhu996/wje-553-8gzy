import { request } from '../utils/request';
import type { Student } from '../types/student';
import type { Enrollment } from '../types/enrollment';
export const studentApi = {
  list: () => request.get<unknown, Student[]>('/students'),
  me: () => request.get<unknown, Student>('/students/me'),
  myEnrollments: () => request.get<unknown, Enrollment[]>('/students/me/enrollments'),
};
