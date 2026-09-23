<script setup lang="ts">
import { onMounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import StatusTag from '../components/common/StatusTag.vue';
import EmptyState from '../components/common/EmptyState.vue';
import { useCourses } from '../hooks/useCourses';
import { useAuthStore } from '../stores/authStore';
import { useStudentStore } from '../stores/studentStore';
import { EnrollmentStatus } from '../constants/enums';
import type { Course } from '../types/course';

const router = useRouter();
const auth = useAuthStore();
const studentStore = useStudentStore();
const filters = reactive({ keyword: '', semester: '', status: '' });
const { courses, loading, fetchCourses, enrollCourse, dropCourse, cancelWaitlist } = useCourses();

onMounted(async () => {
  fetchCourses();
  if (auth.isStudent) {
    try { await studentStore.fetchMe(); } catch { /* 无学生档案时隐藏选课操作 */ }
  }
});

function search() { fetchCourses(Object.fromEntries(Object.entries(filters).filter(([, v]) => v))); }
function openCourse(row: Course) { router.push('/courses/' + row.id); }

async function onEnroll(row: Course) {
  const sid = studentStore.current?.id;
  if (!sid) return;
  const res = await enrollCourse(row.id, sid);
  if (res.status === EnrollmentStatus.WAITLISTED) ElMessage.info(`课程已满，已加入候补队列，当前第 ${res.position} 位`);
  else ElMessage.success('选课成功');
}
async function onDrop(row: Course) {
  const sid = studentStore.current?.id;
  if (!sid) return;
  await dropCourse(row.id, sid);
  ElMessage.success('已退课');
}
async function onCancelWaitlist(row: Course) {
  const sid = studentStore.current?.id;
  if (!sid) return;
  await cancelWaitlist(row.id, sid);
  ElMessage.success('已退出候补队列');
}
</script>

<template>
  <section class="page">
    <header>
      <div><h2>课程管理</h2><p>按角色查看课程、处理开课、选课和状态流转。</p></div>
      <el-button type="primary" v-permission="['ADMIN','TEACHER']">新建课程</el-button>
    </header>
    <el-form class="filters" inline>
      <el-input v-model="filters.keyword" placeholder="课程名或编号" clearable />
      <el-input v-model="filters.semester" placeholder="学期" clearable />
      <el-select v-model="filters.status" placeholder="状态" clearable>
        <el-option label="已发布" value="PUBLISHED" />
        <el-option label="进行中" value="IN_PROGRESS" />
      </el-select>
      <el-button @click="search">筛选</el-button>
    </el-form>
    <el-table v-loading="loading" :data="courses" row-key="id" @row-click="openCourse">
      <el-table-column prop="code" label="编号" width="130" />
      <el-table-column prop="name" label="课程" />
      <el-table-column prop="teacher_name" label="教师" />
      <el-table-column prop="semester" label="学期" />
      <el-table-column label="状态">
        <template #default="{ row }"><StatusTag :status="row.status" type="course" /></template>
      </el-table-column>
      <el-table-column label="入选 / 候补" width="150">
        <template #default="{ row }">{{ row.enrolled_count }}/{{ row.max_students }} 人 · 候补 {{ row.waitlisted_count }}</template>
      </el-table-column>
      <el-table-column v-if="auth.isStudent && studentStore.current" label="操作" width="200">
        <template #default="{ row }">
          <el-button v-if="!row.my_status" size="small" type="primary" @click.stop="onEnroll(row)">
            {{ row.enrolled_count >= row.max_students ? '加入候补' : '选课' }}
          </el-button>
          <el-button v-else-if="row.my_status === EnrollmentStatus.ENROLLED" size="small" type="danger" @click.stop="onDrop(row)">退课</el-button>
          <template v-else>
            <span class="waitlist-position">候补第 {{ row.my_position }} 位</span>
            <el-button size="small" @click.stop="onCancelWaitlist(row)">退出候补</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>
    <EmptyState v-if="!loading && courses.length === 0" message="暂无课程" />
  </section>
</template>

<style scoped>
.waitlist-position { margin-right: 8px; color: #e6a23c; font-size: 13px; }
</style>
