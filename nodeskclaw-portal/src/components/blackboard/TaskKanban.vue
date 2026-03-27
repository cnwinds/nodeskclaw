<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Archive, AlertCircle, Clock, CheckCircle2, Play, Plus, Loader2, DollarSign } from 'lucide-vue-next'
import { useWorkspaceStore, type TaskInfo } from '@/stores/workspace'
import { useI18n } from 'vue-i18n'
import MentionPicker from './MentionPicker.vue'
import { encodeMentionNamesToTokens, replaceMentionTokens, type MentionSelection } from '@/utils/mentionText'

const props = withDefaults(defineProps<{
  workspaceId: string
  canEdit?: boolean
}>(), {
  canEdit: true,
})

const { t } = useI18n()
const store = useWorkspaceStore()

const tasks = ref<TaskInfo[]>([])
const loading = ref(false)
const showArchived = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const newTitle = ref('')
const newDescription = ref('')
const newPriority = ref<'low' | 'medium' | 'high' | 'urgent'>('medium')
const newEstimatedValue = ref<number | null>(null)
const newMentions = ref<MentionSelection[]>([])
const descriptionTextareaRef = ref<HTMLTextAreaElement | null>(null)
const mentionPickerRef = ref<InstanceType<typeof MentionPicker> | null>(null)

const columns = computed(() => [
  { key: 'pending', label: t('blackboard.taskPending'), icon: Clock, color: 'text-yellow-500' },
  { key: 'in_progress', label: t('blackboard.taskInProgress'), icon: Play, color: 'text-blue-500' },
  { key: 'done', label: t('blackboard.taskDone'), icon: CheckCircle2, color: 'text-green-500' },
  { key: 'blocked', label: t('blackboard.taskBlocked'), icon: AlertCircle, color: 'text-red-500' },
])

function formatMentionText(raw: string | null | undefined): string {
  return replaceMentionTokens(
    raw || '',
    store.currentWorkspace?.agents || [],
    store.members,
    t('chat.mentionAll'),
  )
}

function tasksByStatus(status: string) {
  return tasks.value.filter(t => t.status === status)
}

async function loadTasks() {
  loading.value = true
  try {
    tasks.value = await store.fetchTasks(props.workspaceId, undefined, !showArchived.value)
  } finally {
    loading.value = false
  }
}

function extractMentionedAssigneeId(...texts: string[]): string | undefined {
  const mentionRe = /@agent:([a-f0-9\-]{36})/i
  for (const text of texts) {
    const matched = mentionRe.exec(text)
    if (matched?.[1]) return matched[1]
  }
  return undefined
}

async function createTask() {
  if (!props.canEdit || !newTitle.value.trim()) return
  creating.value = true
  try {
    const payload: {
      title: string
      description?: string
      priority?: 'low' | 'medium' | 'high' | 'urgent'
      assignee_id?: string
      estimated_value?: number
    } = {
      title: encodeMentionNamesToTokens(newTitle.value.trim(), newMentions.value),
      priority: newPriority.value,
    }
    const description = encodeMentionNamesToTokens(newDescription.value.trim(), newMentions.value)
    if (description) payload.description = description
    if (newEstimatedValue.value != null) payload.estimated_value = newEstimatedValue.value
    const assigneeId = extractMentionedAssigneeId(payload.title, payload.description || '')
    if (assigneeId) payload.assignee_id = assigneeId

    await store.createTask(props.workspaceId, payload)
    newTitle.value = ''
    newDescription.value = ''
    newMentions.value = []
    newPriority.value = 'medium'
    newEstimatedValue.value = null
    showCreate.value = false
    await loadTasks()
  } finally {
    creating.value = false
  }
}

const editingValueTaskId = ref<string | null>(null)
const valueInput = ref<number | null>(null)

async function onArchive(taskId: string) {
  await store.archiveTask(props.workspaceId, taskId)
  await loadTasks()
}

function startValueEdit(task: TaskInfo) {
  editingValueTaskId.value = task.id
  valueInput.value = task.actual_value
}

async function saveValue(taskId: string) {
  if (valueInput.value != null) {
    await store.updateTask(props.workspaceId, taskId, { actual_value: valueInput.value })
    await loadTasks()
  }
  editingValueTaskId.value = null
}

function priorityBadgeClass(priority: string) {
  const map: Record<string, string> = {
    urgent: 'bg-red-500/20 text-red-400',
    high: 'bg-orange-500/20 text-orange-400',
    medium: 'bg-blue-500/20 text-blue-400',
    low: 'bg-zinc-500/20 text-zinc-400',
  }
  return map[priority] || map.medium
}

onMounted(loadTasks)
watch(showArchived, loadTasks)

defineExpose({ refresh: loadTasks })
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <h3 class="text-sm font-medium text-muted-foreground">{{ t('blackboard.tasks') }}</h3>
        <button
          v-if="canEdit"
          class="flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          @click="showCreate = !showCreate"
        >
          <Plus class="w-3.5 h-3.5" />
          {{ t('blackboard.newTask') }}
        </button>
      </div>
      <button
        role="switch"
        :aria-checked="showArchived"
        class="flex items-center gap-2 text-xs text-muted-foreground"
        @click="showArchived = !showArchived"
      >
        <span>{{ t('blackboard.showArchived') }}</span>
        <span
          class="relative inline-flex h-4 w-7 shrink-0 rounded-full border border-border transition-colors"
          :class="showArchived ? 'bg-primary border-primary' : 'bg-muted'"
        >
          <span
            class="pointer-events-none block h-3 w-3 rounded-full bg-background shadow-sm transition-transform"
            :class="showArchived ? 'translate-x-3' : 'translate-x-0'"
          />
        </span>
      </button>
    </div>

    <div v-if="showCreate && canEdit" class="border border-border rounded-lg p-3 space-y-2 bg-muted/30">
      <input
        v-model="newTitle"
        class="w-full bg-background border border-border rounded px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50"
        :placeholder="t('blackboard.taskTitlePlaceholder')"
      />
      <div class="grid grid-cols-2 gap-2">
        <select
          v-model="newPriority"
          class="bg-background border border-border rounded px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-primary/50"
        >
          <option value="low">{{ t('blackboard.priorityLow') }}</option>
          <option value="medium">{{ t('blackboard.priorityMedium') }}</option>
          <option value="high">{{ t('blackboard.priorityHigh') }}</option>
          <option value="urgent">{{ t('blackboard.priorityUrgent') }}</option>
        </select>
        <input
          v-model.number="newEstimatedValue"
          type="number"
          step="0.1"
          min="0"
          class="bg-background border border-border rounded px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-primary/50"
          :placeholder="t('blackboard.estimatedValue')"
        />
      </div>
      <div class="relative">
        <textarea
          ref="descriptionTextareaRef"
          v-model="newDescription"
          rows="3"
          class="w-full bg-background border border-border rounded px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary/50 resize-none"
          :placeholder="t('blackboard.taskDescriptionPlaceholder')"
          @input="mentionPickerRef?.onInput()"
          @keydown="mentionPickerRef?.onKeydown($event)"
        />
        <MentionPicker
          ref="mentionPickerRef"
          v-model="newDescription"
          v-model:mentions="newMentions"
          :textarea-el="descriptionTextareaRef"
        />
      </div>
      <p class="text-[11px] text-muted-foreground">{{ t('blackboard.taskMentionHint') }}</p>
      <div class="flex justify-end gap-2">
        <button
          class="px-3 py-1.5 text-xs rounded-lg bg-muted hover:bg-muted/80 transition-colors"
          @click="showCreate = false"
        >
          {{ t('blackboard.cancel') }}
        </button>
        <button
          class="px-3 py-1.5 text-xs rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1 disabled:opacity-50"
          :disabled="creating || !newTitle.trim()"
          @click="createTask"
        >
          <Loader2 v-if="creating" class="w-3.5 h-3.5 animate-spin" />
          {{ t('blackboard.createTask') }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="flex justify-center py-8">
      <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
    </div>

    <div v-else class="grid grid-cols-4 gap-3">
      <div v-for="col in columns" :key="col.key" class="space-y-2">
        <div class="flex items-center gap-1.5 mb-2">
          <component :is="col.icon" class="w-3.5 h-3.5" :class="col.color" />
          <span class="text-xs font-medium">{{ col.label }}</span>
          <span class="text-xs text-muted-foreground">({{ tasksByStatus(col.key).length }})</span>
        </div>

        <div
          v-for="task in tasksByStatus(col.key)"
          :key="task.id"
          class="p-2.5 rounded-lg bg-muted/50 border border-border/50 space-y-1.5 text-xs"
        >
          <div class="flex items-start justify-between gap-1">
            <span class="font-medium text-sm leading-tight">{{ formatMentionText(task.title) }}</span>
            <span v-if="task.priority" class="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium" :class="priorityBadgeClass(task.priority)">
              {{ task.priority }}
            </span>
          </div>

          <p v-if="task.description" class="text-muted-foreground line-clamp-2">{{ formatMentionText(task.description) }}</p>

          <div v-if="task.assignee_name" class="text-muted-foreground">
            {{ t('blackboard.assignee') }}: {{ task.assignee_name }}
          </div>

          <div class="flex items-center gap-2 text-muted-foreground">
            <span v-if="task.estimated_value != null">{{ t('blackboard.estimatedValue') }}: {{ task.estimated_value }}</span>
            <span v-if="task.actual_value != null">{{ t('blackboard.actualValue') }}: {{ task.actual_value }}</span>
            <span v-if="task.token_cost != null">Token: {{ task.token_cost }}</span>
          </div>

          <div v-if="task.blocker_reason && task.status === 'blocked'" class="text-red-400 text-[11px]">
            {{ task.blocker_reason }}
          </div>

          <div v-if="task.status === 'done'" class="pt-1 flex items-center gap-2">
            <template v-if="editingValueTaskId === task.id">
              <input
                v-model.number="valueInput"
                type="number"
                step="0.1"
                min="0"
                class="w-16 h-5 text-[11px] px-1 rounded border border-border bg-background"
                :placeholder="t('blackboard.actualValue')"
                @keyup.enter="saveValue(task.id)"
                @keyup.escape="editingValueTaskId = null"
              />
              <button
                class="text-[11px] text-green-400 hover:text-green-300 transition-colors"
                @click="saveValue(task.id)"
              >{{ t('blackboard.save') }}</button>
            </template>
            <button
              v-else
              class="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
              @click="startValueEdit(task)"
            >
              <DollarSign class="w-3 h-3" />
              {{ t('blackboard.annotateValue') }}
            </button>
            <button
              v-if="!task.archived_at"
              class="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
              @click="onArchive(task.id)"
            >
              <Archive class="w-3 h-3" />
              {{ t('blackboard.archive') }}
            </button>
          </div>
        </div>

        <div v-if="tasksByStatus(col.key).length === 0" class="text-center text-muted-foreground text-xs py-4">
          {{ t('blackboard.noTasks') }}
        </div>
      </div>
    </div>
  </div>
</template>
