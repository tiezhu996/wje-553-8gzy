<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import StatusTag from '../components/common/StatusTag.vue';
import EmptyState from '../components/common/EmptyState.vue';
import ConfirmDialog from '../components/common/ConfirmDialog.vue';
import { useCourses } from '../hooks/useCourses';
import { useAuth } from '../hooks/useAuth';
import { useStudentStore } from '../stores/studentStore';
import { useEnrollmentStore } from '../stores/enrollmentStore';
import type { Course } from '../types/course';

const router = useRouter();
const filters = reactive({ keyword: '', semester: '', status: '' });
const { courses, loading, fetchCourses, enrollCourse, dropCourse } = useCourses();
const { isStudent } = useAuth();
const studentStore = useStudentStore();
const enrollmentStore = useEnrollmentStore();
const activeTab = ref<'all' | 'mine'>('all');
const dropTarget = ref<Course | null>(null);
const busy = ref(false);

onMounted(async () => {
  await fetchCourses();
  if (isStudent.value) {
    try { await studentStore.fetchMe(); await enrollmentStore.fetchMine(); } catch { /* 非学生账号无档案时忽略 */ }
  }
});

function search() { fetchCourses(Object.fromEntries(Object.entries(filters).filter(([, v]) => v))); }
function openCourse(row: Course) { router.push('/courses/' + row.id); }
function myEnrollment(courseId: string) { return enrollmentStore.myCourseIds.get(courseId); }
const myCourses = computed(() => courses.value.filter((c) => enrollmentStore.myCourseIds.has(c.id)));
const shownCourses = computed(() => (activeTab.value === 'mine' ? myCourses.value : courses.value));

async function handleEnroll(course: Course) {
  if (!studentStore.me) { ElMessage.error('未找到当前学生档案'); return; }
  busy.value = true;
  try {
    const res = await enrollCourse(course.id, studentStore.me.id);
    await enrollmentStore.fetchMine();
    if (res.status === 'ENROLLED') ElMessage.success('选课成功');
    else ElMessage.warning(`课程已满，已进入候补队列，当前排队位置：第 ${res.waitlist_position} 位`);
  } finally { busy.value = false; }
}

async function confirmDrop() {
  const course = dropTarget.value;
  if (!course || !studentStore.me) return;
  busy.value = true;
  try {
    await dropCourse(course.id, studentStore.me.id);
    await enrollmentStore.fetchMine();
    const mine = myEnrollment(course.id);
    ElMessage.success(mine?.status === 'WAITLISTED' ? '已退出候补队列' : '已退课');
  } finally { busy.value = false; dropTarget.value = null; }
}

function actionText(course: Course) {
  const mine = myEnrollment(course.id);
  if (!mine) return { text: '选课', type: 'primary' as const, disabled: false };
  if (mine.status === 'ENROLLED') return { text: '退课', type: 'danger' as const, disabled: false };
  return { text: `候补第 ${mine.waitlist_position} 位 · 退出`, type: 'warning' as const, disabled: false };
}
</script>

<template>
  <section class="page">
    <header>
      <div><h2>课程管理</h2><p>按角色查看课程、处理开课、选课和状态流转。</p></div>
      <el-button type="primary" v-permission="['ADMIN','TEACHER']">新建课程</el-button>
    </header>

    <el-tabs v-if="isStudent" v-model="activeTab" class="course-tabs">
      <el-tab-pane label="全部课程" name="all" />
      <el-tab-pane label="我的课程（已选 / 候补）" name="mine" />
    </el-tabs>

    <el-form class="filters" inline>
      <el-input v-model="filters.keyword" placeholder="课程名或编号" clearable />
      <el-input v-model="filters.semester" placeholder="学期" clearable />
      <el-select v-model="filters.status" placeholder="状态" clearable style="width:140px">
        <el-option label="已发布" value="PUBLISHED" /><el-option label="进行中" value="IN_PROGRESS" />
      </el-select>
      <el-button @click="search">筛选</el-button>
    </el-form>

    <el-table v-loading="loading" :data="shownCourses" row-key="id" @row-click="openCourse">
      <el-table-column prop="code" label="编号" width="130" />
      <el-table-column prop="name" label="课程" />
      <el-table-column prop="teacher_name" label="教师" />
      <el-table-column prop="semester" label="学期" />
      <el-table-column label="状态"><template #default="{ row }"><StatusTag :status="row.status" type="course" /></template></el-table-column>
      <el-table-column label="入选 / 候补 / 容量" width="160">
        <template #default="{ row }">
          <el-tag type="success" effect="plain">{{ row.enrolled_count }} 入选</el-tag>
          <el-tag v-if="row.waitlist_count > 0" type="warning" effect="plain" style="margin-left:4px">{{ row.waitlist_count }} 候补</el-tag>
          <span style="margin-left:4px;color:var(--el-text-color-secondary)">/ {{ row.max_students }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="isStudent" label="我的操作" width="190">
        <template #default="{ row }">
          <template v-if="myEnrollment(row.id)">
            <el-tag v-if="myEnrollment(row.id)?.status === 'ENROLLED'" type="success" size="small">已入选</el-tag>
            <el-tag v-else type="warning" size="small">候补第 {{ myEnrollment(row.id)?.waitlist_position }} 位</el-tag>
            <el-button size="small" :type="actionText(row).type" link :loading="busy" @click.stop="dropTarget = row">
              {{ myEnrollment(row.id)?.status === 'WAITLISTED' ? '退出候补' : '退课' }}
            </el-button>
          </template>
          <el-button v-else size="small" type="primary" link :loading="busy" @click.stop="handleEnroll(row)">
            {{ row.enrolled_count >= row.max_students ? '已满，候补' : '选课' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <EmptyState v-if="!loading && shownCourses.length === 0" :message="activeTab === 'mine' ? '还没有已选或候补的课程' : '暂无课程'" />

    <ConfirmDialog
      :visible="!!dropTarget"
      title="确认操作"
      :message="dropTarget && myEnrollment(dropTarget.id)?.status === 'WAITLISTED' ? `确定退出《${dropTarget.name}》的候补队列吗？` : `确定退选《${dropTarget?.name}》吗？退课后候补同学将自动补位。`"
      @update:visible="(v: boolean) => !v && (dropTarget = null)"
      @confirm="confirmDrop"
    />
  </section>
</template>

<style scoped>
.course-tabs { margin-bottom: 4px; }
.course-tabs :deep(.el-tabs__header) { margin-bottom: 8px; }
</style>
