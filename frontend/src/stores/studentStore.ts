import { defineStore } from 'pinia';
import { studentApi } from '../api/students';
import type { Student } from '../types/student';
export const useStudentStore = defineStore('students', { state: () => ({ items: [] as Student[], current: null as Student | null }), actions: { async fetch() { this.items = await studentApi.list(); }, async fetchMe() { this.current = await studentApi.me(); } } });
