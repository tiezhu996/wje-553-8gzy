import { defineStore } from 'pinia';
import { courseApi } from '../api/courses';
import { studentApi } from '../api/students';
import type { Enrollment } from '../types/enrollment';

export const useEnrollmentStore = defineStore('enrollments', {
  state: () => ({
    roster: [] as Enrollment[],       // 当前课程详情的入选/候补名单
    myEnrollments: [] as Enrollment[], // 当前学生的已选 + 候补
  }),
  getters: {
    enrolled: (s) => s.roster.filter((e) => e.status === 'ENROLLED'),
    waitlisted: (s) => [...s.roster].filter((e) => e.status === 'WAITLISTED').sort((a, b) => (a.waitlist_position ?? 0) - (b.waitlist_position ?? 0)),
    myCourseIds: (s) => new Map(s.myEnrollments.map((e) => [e.course_id, e])),
  },
  actions: {
    async fetchRoster(courseId: string) { this.roster = await courseApi.enrollments(courseId); },
    async fetchMine() { this.myEnrollments = await studentApi.myEnrollments(); },
  },
});
