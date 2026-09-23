<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import StatusTag from '../components/common/StatusTag.vue';
import StudentAvatar from '../components/common/StudentAvatar.vue';
import ScoreDisplay from '../components/common/ScoreDisplay.vue';
import ConfirmDialog from '../components/common/ConfirmDialog.vue';
import { useCourseStore } from '../stores/courseStore';
import { useStudentStore } from '../stores/studentStore';
import { useAssignmentStore } from '../stores/assignmentStore';
import { useAttendanceStore } from '../stores/attendanceStore';
import { useEnrollmentStore } from '../stores/enrollmentStore';
import { useAuth } from '../hooks/useAuth';

const route = useRoute();
const courses = useCourseStore();
const students = useStudentStore();
const assignments = useAssignmentStore();
const attendance = useAttendanceStore();
const enrollments = useEnrollmentStore();
const { isStudent, isAdmin, isTeacher } = useAuth();

const busy = ref(false);
const capacityEditing = ref(false);
const capacityInput = ref(0);
const dropStudentId = ref<string | null>(null);
const dropWaitlisted = ref(false);

onMounted(async () => {
  const id = route.params.id as string;
  await Promise.all([
    courses.fetchOne(id),
    students.fetch(),
    assignments.fetch(id),
    attendance.fetch({ course_id: id }),
    enrollments.fetchRoster(id),
  ]);
  if (isStudent.value) { try { await students.fetchMe(); } catch { /* ignore */ } }
});

const course = computed(() => courses.current);
const enrolledRows = computed(() => enrollments.enrolled);
const waitlistRows = computed(() => enrollments.waitlisted);
const studentMap = computed(() => new Map(students.items.map((s) => [s.id, s])));
function of(studentId: string) { return studentMap.value.get(studentId); }
const myRecord = computed(() => (isStudent.value && students.me ? enrollments.roster.find((e) => e.student_id === students.me!.id) ?? null : null));

function startEditCapacity() {
  if (!course.value) return;
  capacityInput.value = course.value.max_students;
  capacityEditing.value = true;
}
async function saveCapacity() {
  if (!course.value) return;
  if (!Number.isInteger(capacityInput.value) || capacityInput.value < 1) { ElMessage.error('容量必须为大于 0 的整数'); return; }
  if (capacityInput.value === course.value.max_students) { capacityEditing.value = false; return; }
  busy.value = true;
  try {
    await courses.update(course.value.id, { max_students: capacityInput.value });
    await Promise.all([enrollments.fetchRoster(course.value.id)]);
    ElMessage.success('容量已更新');
    capacityEditing.value = false;
  } catch {
    // 错误信息已由请求拦截器统一提示（含“还差多少人”）
    if (course.value) capacityInput.value = course.value.max_students;
  } finally { busy.value = false; }
}

async function enrollMe() {
  if (!course.value || !students.me) return;
  busy.value = true;
  try {
    const res = await courses.enroll(course.value.id, students.me.id);
    await enrollments.fetchRoster(course.value.id);
    if (res.status === 'ENROLLED') ElMessage.success('选课成功');
    else ElMessage.warning(`课程已满，已进入候补队列，当前排队位置：第 ${res.waitlist_position} 位`);
  } finally { busy.value = false; }
}

function askDrop(studentId: string, waitlisted: boolean) {
  dropStudentId.value = studentId;
  dropWaitlisted.value = waitlisted;
}
async function confirmDrop() {
  if (!course.value || !dropStudentId.value) return;
  const targetId = dropStudentId.value;
  busy.value = true;
  try {
    await courses.drop(course.value.id, targetId);
    await enrollments.fetchRoster(course.value.id);
    ElMessage.success(dropWaitlisted.value ? '候补学生已移出队列' : '已退课，候补队首自动补位');
  } finally { busy.value = false; dropStudentId.value = null; }
}
</script>

<template>
  <section class="page" v-if="course">
    <header>
      <div>
        <h2>{{ course.name }}</h2>
        <p>{{ course.code }} · {{ course.teacher_name }} · {{ course.semester }}</p>
        <p class="counts">
          <el-tag type="success" effect="light">已入选 {{ course.enrolled_count }} 人</el-tag>
          <el-tag type="warning" effect="light" style="margin-left:8px">候补 {{ course.waitlist_count }} 人</el-tag>
          <el-tag type="info" effect="plain" style="margin-left:8px">容量 {{ course.max_students }} 人</el-tag>
          <el-tag v-if="course.enrolled_count >= course.max_students" type="danger" effect="plain" size="small" style="margin-left:8px">已满</el-tag>
        </p>
      </div>
      <div class="header-actions">
        <StatusTag :status="course.status" type="course" />
        <el-button v-if="isAdmin || isTeacher" size="small" @click="startEditCapacity">调整容量</el-button>
        <template v-if="isStudent">
          <el-tag v-if="myRecord?.status === 'ENROLLED'" type="success">我：已入选</el-tag>
          <el-tag v-else-if="myRecord?.status === 'WAITLISTED'" type="warning">我：候补第 {{ myRecord.waitlist_position }} 位</el-tag>
          <el-button v-if="myRecord" size="small" type="danger" :loading="busy" @click="askDrop(myRecord.student_id, myRecord.status === 'WAITLISTED')">
            {{ myRecord.status === 'WAITLISTED' ? '退出候补' : '退课' }}
          </el-button>
          <el-button v-else size="small" type="primary" :loading="busy" @click="enrollMe">
            {{ course.enrolled_count >= course.max_students ? '课程已满，加入候补' : '选课' }}
          </el-button>
        </template>
      </div>
    </header>

    <el-dialog v-model="capacityEditing" title="调整课程容量" width="360px">
      <el-input-number v-model="capacityInput" :min="1" :step="1" />
      <p style="color:var(--el-text-color-secondary);font-size:12px;margin-top:8px">
        当前已入选 {{ course.enrolled_count }} 人；容量调低到少于该人数将被拒绝。调高后候补学生将按排队顺序自动补位。
      </p>
      <template #footer>
        <el-button @click="capacityEditing = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="saveCapacity">保存</el-button>
      </template>
    </el-dialog>

    <el-tabs>
      <el-tab-pane :label="`入选名单（${enrolledRows.length}）`">
        <el-table :data="enrolledRows">
          <el-table-column label="排队位置" width="90">
            <template #default><span style="color:var(--el-text-color-secondary)">—</span></template>
          </el-table-column>
          <el-table-column label="学生">
            <template #default="{ row }"><StudentAvatar :student="of(row.student_id)" :fallback="row.student_id" /></template>
          </el-table-column>
          <el-table-column label="年级"><template #default="{ row }">{{ of(row.student_id)?.grade }}</template></el-table-column>
          <el-table-column label="邮箱"><template #default="{ row }">{{ of(row.student_id)?.email }}</template></el-table-column>
          <el-table-column label="状态" width="100"><template #default><el-tag type="success" size="small">已入选</el-tag></template></el-table-column>
          <el-table-column v-if="isAdmin || isTeacher" label="操作" width="100">
            <template #default="{ row }"><el-button size="small" type="danger" link @click="askDrop(row.student_id, false)">移除</el-button></template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane :label="`候补队列（${waitlistRows.length}）`">
        <el-table :data="waitlistRows">
          <el-table-column label="排队位置" width="90">
            <template #default="{ row }"><el-tag type="warning" size="small">第 {{ row.waitlist_position }} 位</el-tag></template>
          </el-table-column>
          <el-table-column label="学生">
            <template #default="{ row }"><StudentAvatar :student="of(row.student_id)" :fallback="row.student_id" /></template>
          </el-table-column>
          <el-table-column label="提交时间"><template #default="{ row }">{{ row.created_at }}</template></el-table-column>
          <el-table-column label="操作" v-if="isStudent || isAdmin || isTeacher">
            <template #default="{ row }">
              <el-button v-if="isStudent && students.me?.id === row.student_id" size="small" type="warning" link @click="askDrop(row.student_id, true)">退出候补</el-button>
              <el-button v-else-if="isAdmin || isTeacher" size="small" type="danger" link @click="askDrop(row.student_id, true)">移出候补</el-button>
            </template>
          </el-table-column>
        </el-table>
        <p v-if="waitlistRows.length === 0" style="color:var(--el-text-color-secondary)">暂无候补学生；有学生退课时，等待最久的候补者会自动补位。</p>
      </el-tab-pane>

      <el-tab-pane label="作业列表">
        <el-table :data="assignments.items">
          <el-table-column prop="title" label="标题" /><el-table-column prop="type" label="类型" />
          <el-table-column label="状态"><template #default="{ row }"><StatusTag :status="row.status" type="assignment" /></template></el-table-column>
          <el-table-column prop="submissions_count" label="提交" />
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="考勤记录">
        <el-table :data="attendance.items">
          <el-table-column prop="student_name" label="学生" /><el-table-column prop="date" label="日期" />
          <el-table-column label="状态"><template #default="{ row }"><StatusTag :status="row.status" type="attendance" /></template></el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="成绩汇总">
        <el-table :data="enrolledRows">
          <el-table-column label="学生">
            <template #default="{ row }"><StudentAvatar :student="of(row.student_id)" :fallback="row.student_id" /></template>
          </el-table-column>
          <el-table-column label="综合分"><template #default><ScoreDisplay :score="86" :total-score="100" show-bar /></template></el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <ConfirmDialog
      :visible="!!dropStudentId"
      title="确认操作"
      :message="dropWaitlisted ? '确定将该学生移出候补队列吗？' : '确定将该学生移出课程吗？候补队首会自动补位。'"
      @update:visible="(v: boolean) => !v && (dropStudentId = null)"
      @confirm="confirmDrop"
    />
  </section>
</template>

<style scoped>
.counts { margin: 8px 0 0; }
.header-actions { display: flex; align-items: center; gap: 8px; }
</style>
