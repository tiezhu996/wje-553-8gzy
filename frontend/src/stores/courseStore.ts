import { defineStore } from 'pinia';
import { courseApi } from '../api/courses';
import type { Course, CoursePayload } from '../types/course';
import type { EnrollResult } from '../types/enrollment';
export const useCourseStore = defineStore('courses', {
  state: () => ({ items: [] as Course[], current: null as Course | null, loading: false }),
  actions: {
    async fetch(params?: Record<string,string>) { this.loading = true; try { this.items = await courseApi.list(params); } finally { this.loading = false; } },
    async fetchOne(id: string) { this.current = await courseApi.get(id); },
    async update(id: string, payload: Partial<CoursePayload>) { const updated = await courseApi.update(id, payload); await this.fetch(); if (this.current) this.current = updated; return updated; },
    async updateStatus(id: string, status: Course['status']) { await this.update(id, { status }); },
    /** 选课：返回入选或候补结果，由页面提示排队位置 */
    async enroll(courseId: string, studentId: string): Promise<EnrollResult> { const res = await courseApi.enroll(courseId, studentId); await this.fetch(); if (this.current) await this.fetchOne(courseId); return res; },
    /** 退课 / 退出候补 */
    async drop(courseId: string, studentId: string) { await courseApi.drop(courseId, studentId); await this.fetch(); if (this.current) await this.fetchOne(courseId); },
  },
});
