<template>
  <section class="page" data-module="firealarm">
    <header class="page-head">
      <div>
        <h2>消防设施管理</h2>
        <p class="page-desc">
          按灭火剂量与有效期分档盯防：按月查看快到期与已过期设施，过期与压力不足分开标出；
          勾选一批即可批量登记检查，已过期的单独退回、先安排更换才进下一轮。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记消防设施</button>
        <button class="btn" type="button" @click="exportRows">导出设施清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in summaryCards" :key="item.label" class="stat-card" :class="item.tone">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <nav class="tabs">
      <button
        v-for="tab in tabItems"
        :key="tab.key"
        type="button"
        class="tab"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
        <em v-if="tab.badge" class="tab-badge">{{ tab.badge }}</em>
      </button>
    </nav>

    <!-- 有效期看板 -->
    <div v-if="activeTab === 'overview'" class="tab-panel">
      <p class="hint">统计基准日 {{ overview.today }}，快到期口径为 {{ overview.within_days }} 天内；过期与压力不足分开展示。</p>

      <section class="group-section">
        <h3 class="group-title expired-text">已过期（{{ overview.summary.expired_count }}）</h3>
        <p v-if="!overview.expired_by_month.length" class="empty-inline">暂无过期设施</p>
        <div v-for="group in overview.expired_by_month" :key="group.month" class="month-block">
          <h4 class="month-title">
            {{ group.month }}
            <span class="month-count expired-text">{{ group.count }} 台</span>
          </h4>
          <table class="data-table">
            <thead>
              <tr><th>设施编号</th><th>设施类型</th><th>所属站点</th><th>灭火剂量</th><th>有效期至</th><th>标记</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="row in group.facilities" :key="row.id">
                <td>{{ row.设施编号 }}</td>
                <td>{{ row.设施类型 }}</td>
                <td>{{ row.所属站点 }}</td>
                <td>{{ row.灭火剂量 }}</td>
                <td>{{ row.有效期至 }}（已过期 {{ expiredDays(row) }} 天）</td>
                <td>
                  <span class="tag tag-expired">已过期</span>
                  <span v-if="row.压力不足" class="tag tag-pressure">压力不足</span>
                </td>
                <td><button class="link" type="button" @click="replaceFacility(row.id)">安排更换</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="group-section">
        <h3 class="group-title soon-text">{{ overview.within_days }} 天内快到期（{{ overview.summary.expiring_soon_count }}）</h3>
        <p v-if="!overview.expiring_by_month.length" class="empty-inline">近期暂无到期设施</p>
        <div v-for="group in overview.expiring_by_month" :key="group.month" class="month-block">
          <h4 class="month-title">
            {{ group.month }}
            <span class="month-count soon-text">{{ group.count }} 台</span>
          </h4>
          <table class="data-table">
            <thead>
              <tr><th>设施编号</th><th>设施类型</th><th>所属站点</th><th>灭火剂量</th><th>有效期至</th><th>剩余天数</th><th>标记</th></tr>
            </thead>
            <tbody>
              <tr v-for="row in group.facilities" :key="row.id">
                <td>{{ row.设施编号 }}</td>
                <td>{{ row.设施类型 }}</td>
                <td>{{ row.所属站点 }}</td>
                <td>{{ row.灭火剂量 }}</td>
                <td>{{ row.有效期至 }}</td>
                <td><span class="tag tag-soon">{{ row.剩余天数 }} 天</span></td>
                <td><span v-if="row.压力不足" class="tag tag-pressure">压力不足</span><span v-else>—</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="group-section">
        <h3 class="group-title pressure-text">压力不足（{{ overview.low_pressure.length }}）</h3>
        <p v-if="!overview.low_pressure.length" class="empty-inline">暂无压力不足设施</p>
        <table v-else class="data-table">
          <thead>
            <tr><th>设施编号</th><th>设施类型</th><th>所属站点</th><th>灭火剂量</th><th>有效期至</th><th>上次检查</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in overview.low_pressure" :key="row.id">
              <td>{{ row.设施编号 }}</td>
              <td>{{ row.设施类型 }}</td>
              <td>{{ row.所属站点 }}</td>
              <td>{{ row.灭火剂量 }}</td>
              <td>{{ row.有效期至 }}（剩 {{ row.剩余天数 }} 天）</td>
              <td>{{ row.上次检查 ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>

    <!-- 设施台账 -->
    <div v-if="activeTab === 'ledger'" class="tab-panel">
      <form class="filter-bar" @submit.prevent="reloadLedger">
        <label class="filter-item">
          <span>关键字</span>
          <input v-model="filters.keyword" placeholder="设施编号 / 类型 / 站点" />
        </label>
        <label class="filter-item">
          <span>实时状态</span>
          <select v-model="filters.status">
            <option value="">全部</option>
            <option v-for="s in filterOptions.statuses" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <label class="filter-item">
          <span>灭火剂量档</span>
          <select v-model="filters.agent">
            <option value="">全部</option>
            <option v-for="t in filterOptions.agent_tiers" :key="t" :value="t">{{ t }}</option>
          </select>
        </label>
        <label class="filter-item">
          <span>有效期档</span>
          <select v-model="filters.expiry">
            <option value="">全部</option>
            <option v-for="t in filterOptions.expiry_tiers" :key="t" :value="t">{{ t }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetFilters">重置</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>设施编号</th><th>设施类型</th><th>所属站点</th><th>灭火剂量</th>
            <th>上次检查</th><th>有效期至</th><th>检查人员</th><th>状态标记</th><th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in ledger" :key="row.id">
            <td>{{ row.设施编号 }}</td>
            <td>{{ row.设施类型 }}</td>
            <td>{{ row.所属站点 }}</td>
            <td>{{ row.灭火剂量 }}<small class="sub-text">{{ row.灭火剂量档 }}</small></td>
            <td>{{ row.上次检查 ?? '—' }}</td>
            <td>
              {{ row.有效期至 }}
              <small v-if="row.剩余天数 !== null" class="sub-text" :class="daysClass(row)">
                {{ row.已更换 ? '已更换' : (row.过期 ? `已过期 ${expiredDays(row)} 天` : `剩 ${row.剩余天数} 天`) }}
              </small>
            </td>
            <td>{{ row.检查人员 ?? '—' }}</td>
            <td class="tag-cell">
              <span v-if="row.已更换" class="tag tag-replaced">已更换</span>
              <template v-else>
                <span v-if="row.过期" class="tag tag-expired">已过期</span>
                <span v-if="row.压力不足" class="tag tag-pressure">压力不足</span>
                <span v-if="!row.过期 && !row.压力不足" class="tag tag-ok">合格</span>
              </template>
            </td>
            <td class="row-actions">
              <button class="link" type="button" @click="runAction('登记不足', row)">登记不足</button>
              <button class="link" type="button" @click="runAction('登记过期', row)">登记过期</button>
              <button class="link danger-text" type="button" @click="replaceFacility(row.id)">安排更换</button>
            </td>
          </tr>
          <tr v-if="!ledger.length">
            <td colspan="9" class="empty-state">当前筛选条件下没有消防设施</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot"><span>共 {{ ledgerTotal }} 条</span><span v-if="message" class="error-text">{{ message }}</span></footer>
    </div>

    <!-- 批量检查 -->
    <div v-if="activeTab === 'batch'" class="tab-panel">
      <div class="batch-toolbar">
        <label class="filter-item">
          <span>检查人员</span>
          <input v-model="batchForm.inspector" placeholder="本次检查人员姓名" />
        </label>
        <label class="filter-item">
          <span>所属站点</span>
          <select v-model="batchForm.site" @change="reloadChecklist">
            <option value="">全部站点</option>
            <option v-for="s in filterOptions.sites" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <label class="filter-item grow">
          <span>检查备注（可选）</span>
          <input v-model="batchForm.remark" placeholder="整批共用，如：10 月月度检查" />
        </label>
        <button class="btn primary" type="button" :disabled="submitting" @click="submitBatch">
          {{ submitting ? '提交中…' : `登记本次检查（已选 ${selectedIds.size} 台）` }}
        </button>
        <button class="btn ghost" type="button" @click="startNewBatch">开始新一批</button>
      </div>
      <p class="hint">
        当前批次号：<code>{{ batchForm.batch_id }}</code>，同一批次号重复提交只记一次。
        下一轮清单共 {{ checklist.length }} 台；已过期、已更换的设施不会排进清单。
      </p>

      <table class="data-table">
        <thead>
          <tr>
            <th class="check-col"><input type="checkbox" :checked="allSelected" :indeterminate.prop="someSelected" @change="toggleAll" /></th>
            <th>设施编号</th><th>设施类型</th><th>所属站点</th><th>灭火剂量</th>
            <th>上次检查日期</th><th>上次检查人员</th><th>有效期至</th><th>当前标记</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in checklist" :key="row.id">
            <td><input type="checkbox" :value="row.id" v-model="batchSelection" /></td>
            <td>{{ row.设施编号 }}</td>
            <td>{{ row.设施类型 }}</td>
            <td>{{ row.所属站点 }}</td>
            <td>{{ row.灭火剂量 }}<small class="sub-text">{{ row.灭火剂量档 }}</small></td>
            <td>{{ row.上次检查日期 ?? '从未检查' }}</td>
            <td>{{ row.上次检查人员 ?? '—' }}</td>
            <td>{{ row.有效期至 }}（剩 {{ row.剩余天数 }} 天）</td>
            <td class="tag-cell">
              <span v-if="row.压力不足" class="tag tag-pressure">压力不足</span>
              <span v-else class="tag tag-ok">合格</span>
            </td>
          </tr>
          <tr v-if="!checklist.length">
            <td colspan="9" class="empty-state">下一轮没有需要检查的设施（已过期设施请先在看板里安排更换）</td>
          </tr>
        </tbody>
      </table>

      <div v-if="batchResult" class="result-panel" :class="{ 'is-duplicate': batchResult.duplicate }">
        <h4>{{ batchResult.duplicate ? '重复提交已拦截' : '批次登记结果' }}</h4>
        <p class="result-message">{{ batchResult.message }}</p>

        <template v-if="!batchResult.duplicate">
          <section v-if="batchResult.recorded?.length" class="result-section">
            <h5 class="ok-text">已落检查记录（{{ batchResult.recorded.length }} 台）</h5>
            <ul class="result-list">
              <li v-for="item in batchResult.recorded" :key="item.facility_id">
                {{ item.设施编号 }} · {{ item.所属站点 }}
                <span v-if="item.result === '压力不足'" class="tag tag-pressure">压力不足，需处置</span>
                <span v-else class="tag tag-ok">正常</span>
              </li>
            </ul>
          </section>

          <section v-if="batchResult.rejected_expired?.length" class="result-section">
            <h5 class="expired-text">已过期，单独退回（{{ batchResult.rejected_expired.length }} 台）——请先安排更换</h5>
            <ul class="result-list">
              <li v-for="item in batchResult.rejected_expired" :key="item.facility_id" class="rejected-item">
                <span>{{ item.设施编号 }} · {{ item.所属站点 }} · {{ item.reason }}</span>
                <button class="link danger-text" type="button" @click="replaceFacility(item.facility_id, true)">安排更换</button>
              </li>
            </ul>
          </section>

          <section v-if="batchResult.skipped_replaced?.length" class="result-section">
            <h5>已更换，不再检查（{{ batchResult.skipped_replaced.length }} 台）</h5>
            <ul class="result-list">
              <li v-for="item in batchResult.skipped_replaced" :key="item.facility_id">{{ item.设施编号 }}：{{ item.reason }}</li>
            </ul>
          </section>
        </template>
      </div>
      <p v-if="message" class="error-text">{{ message }}</p>
    </div>

    <!-- 检查记录 -->
    <div v-if="activeTab === 'records'" class="tab-panel">
      <table class="data-table">
        <thead>
          <tr><th>检查日期</th><th>设施编号</th><th>所属站点</th><th>检查人员</th><th>检查结果</th><th>所属批次</th><th>备注</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in records" :key="item.id">
            <td>{{ item.check_date }}</td>
            <td>{{ item.设施编号 ?? `#${item.facility_id}` }}</td>
            <td>{{ item.所属站点 ?? '—' }}</td>
            <td>{{ item.inspector }}</td>
            <td>
              <span class="tag" :class="item.result === '压力不足' ? 'tag-pressure' : 'tag-ok'">{{ item.result }}</span>
            </td>
            <td><code>{{ item.batch_id }}</code></td>
            <td>{{ item.remark || '—' }}</td>
          </tr>
          <tr v-if="!records.length"><td colspan="7" class="empty-state">还没有检查记录</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 登记弹窗 -->
    <div v-if="createOpen" class="modal-mask" @click.self="createOpen = false">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记消防设施</h3>
        <label v-for="field in createFields" :key="field" class="filter-item">
          <span>{{ field }}</span>
          <input v-model="createForm[field]" :placeholder="field === '有效期至' ? 'YYYY-MM-DD' : `请输入${field}`" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="createOpen = false">取消</button>
          <button class="btn primary" type="submit">保存登记</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const ENDPOINT = '/api/firealarm'

interface Facility {
  id: number
  设施编号: string
  设施类型: string
  所属站点: string
  灭火剂量: string
  灭火剂量档: string
  压力状态: string
  上次检查: string | null
  有效期至: string
  有效期档: string
  检查人员: string | null
  剩余天数: number | null
  过期: boolean
  压力不足: boolean
  已更换: boolean
  实时状态: string
  纳入检查清单: boolean
  上次检查日期?: string | null
  上次检查人员?: string | null
}

interface MonthGroup {
  month: string
  count: number
  facilities: Facility[]
}

interface Overview {
  today: string
  within_days: number
  summary: { total: number; expired_count: number; expiring_soon_count: number; low_pressure_count: number; replaced_count: number }
  expired_by_month: MonthGroup[]
  expiring_by_month: MonthGroup[]
  low_pressure: Facility[]
}

interface CheckRecord {
  id: number
  facility_id: number
  batch_id: string
  check_date: string
  inspector: string
  result: string
  remark: string | null
  设施编号: string | null
  所属站点: string | null
}

interface BatchResult {
  ok: boolean
  duplicate: boolean
  message: string
  batch?: Record<string, string | number>
  recorded?: { facility_id: number; 设施编号: string; 所属站点: string; result: string; check_date: string }[]
  rejected_expired?: { facility_id: number; 设施编号: string; 所属站点: string; 有效期至: string; reason: string }[]
  skipped_replaced?: { facility_id: number; 设施编号: string; reason: string }[]
  missing_ids?: number[]
}

const TAB_DEFS = [
  { key: 'overview', label: '有效期看板' },
  { key: 'ledger', label: '设施台账' },
  { key: 'batch', label: '批量检查' },
  { key: 'records', label: '检查记录' },
] as const

type TabKey = (typeof TAB_DEFS)[number]['key']
const activeTab = ref<TabKey>('overview')
const message = ref('')
const submitting = ref(false)

const overview = ref<Overview>({
  today: '', within_days: 30,
  summary: { total: 0, expired_count: 0, expiring_soon_count: 0, low_pressure_count: 0, replaced_count: 0 },
  expired_by_month: [], expiring_by_month: [], low_pressure: [],
})

const filterOptions = ref<{ statuses: string[]; agent_tiers: string[]; expiry_tiers: string[]; sites: string[] }>({
  statuses: [], agent_tiers: [], expiry_tiers: [], sites: [],
})

const summaryCards = computed(() => [
  { label: '设施总数', value: overview.value.summary.total, tone: '' },
  { label: '已过期', value: overview.value.summary.expired_count, tone: overview.value.summary.expired_count ? 'card-danger' : '' },
  { label: `${overview.value.within_days} 天内快到期`, value: overview.value.summary.expiring_soon_count, tone: overview.value.summary.expiring_soon_count ? 'card-warn' : '' },
  { label: '压力不足', value: overview.value.summary.low_pressure_count, tone: overview.value.summary.low_pressure_count ? 'card-warn' : '' },
  { label: '已更换归档', value: overview.value.summary.replaced_count, tone: '' },
])

const tabBadges = computed<Record<TabKey, number>>(() => ({
  overview: overview.value.summary.expired_count,
  ledger: 0,
  batch: 0,
  records: 0,
}))
const tabItems = computed(() =>
  TAB_DEFS.map((tab) => ({ ...tab, badge: tabBadges.value[tab.key] })),
)

// ---- 台账 ----
const ledger = ref<Facility[]>([])
const ledgerTotal = ref(0)
const filters = reactive({ keyword: '', status: '', agent: '', expiry: '' })

// ---- 批量检查 ----
const checklist = ref<Facility[]>([])
const batchSelection = ref<number[]>([])
const batchResult = ref<BatchResult | null>(null)
const batchForm = reactive({
  batch_id: newBatchId(),
  inspector: session.operator,
  site: '',
  remark: '',
})
const selectedIds = computed(() => new Set(batchSelection.value))
const allSelected = computed(() => checklist.value.length > 0 && batchSelection.value.length === checklist.value.length)
const someSelected = computed(() => batchSelection.value.length > 0 && !allSelected.value)

// ---- 检查记录 ----
const records = ref<CheckRecord[]>([])

// ---- 登记弹窗 ----
const createOpen = ref(false)
const createError = ref('')
const createFields = ['设施编号', '设施类型', '所属站点', '灭火剂量', '有效期至'] as const
const createForm = reactive<Record<string, string>>({ 设施编号: '', 设施类型: '', 所属站点: '', 灭火剂量: '', 有效期至: '' })

function newBatchId(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `CHK-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${Math.floor(1000 + Math.random() * 9000)}`
}

function expiredDays(row: Facility): number {
  return row.剩余天数 === null ? 0 : -row.剩余天数
}

function daysClass(row: Facility): string {
  if (row.已更换) return 'sub-replaced'
  if (row.过期) return 'sub-expired'
  if ((row.剩余天数 ?? 999) <= overview.value.within_days) return 'sub-soon'
  return ''
}

async function loadOverview() {
  const response = await request(`${ENDPOINT}/expiry-overview`)
  if (response.ok) overview.value = await response.json()
}

async function loadFilters() {
  const response = await request(`${ENDPOINT}/filters`)
  if (response.ok) filterOptions.value = await response.json()
}

async function reloadLedger() {
  message.value = ''
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value) })
  params.set('size', '200')
  const response = await request(`${ENDPOINT}?${params.toString()}`)
  if (!response.ok) { message.value = '设施台账读取失败'; return }
  const payload = await response.json()
  ledger.value = payload.items ?? []
  ledgerTotal.value = payload.total ?? 0
}

function resetFilters() {
  Object.keys(filters).forEach((key) => { filters[key as keyof typeof filters] = '' })
  void reloadLedger()
}

async function reloadChecklist() {
  const params = new URLSearchParams()
  if (batchForm.site) params.set('site', batchForm.site)
  const response = await request(`${ENDPOINT}/checklist?${params.toString()}`)
  if (!response.ok) { message.value = '检查清单读取失败'; return }
  checklist.value = await response.json()
  const valid = new Set(checklist.value.map((row) => row.id))
  batchSelection.value = batchSelection.value.filter((id) => valid.has(id))
}

async function reloadRecords() {
  const response = await request(`${ENDPOINT}/checks`)
  if (response.ok) {
    const payload = await response.json()
    records.value = payload.items ?? []
  }
}

async function refreshAll() {
  await loadOverview()
  await Promise.all([reloadLedger(), reloadChecklist(), reloadRecords()])
}

function switchTab(key: TabKey) {
  activeTab.value = key
  if (key === 'ledger') void reloadLedger()
  if (key === 'batch') void reloadChecklist()
  if (key === 'records') void reloadRecords()
}

function toggleAll(event: Event) {
  batchSelection.value = (event.target as HTMLInputElement).checked ? checklist.value.map((row) => row.id) : []
}

function startNewBatch() {
  batchForm.batch_id = newBatchId()
  batchForm.remark = ''
  batchResult.value = null
  batchSelection.value = []
  message.value = ''
}

async function submitBatch() {
  message.value = ''
  if (!batchForm.inspector.trim()) { message.value = '请填写检查人员'; return }
  if (!batchSelection.value.length) { message.value = '请至少勾选一台设施'; return }
  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/batch-checks`, {
      method: 'POST',
      body: JSON.stringify({
        batch_id: batchForm.batch_id,
        inspector: batchForm.inspector.trim(),
        facility_ids: batchSelection.value,
        remark: batchForm.remark.trim() || null,
      }),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail ?? '批量登记失败')
    batchResult.value = payload
    // 提交后刷新清单：刚登记过的仍会在（下次还可检），已过期/已更换的始终不在。
    await Promise.all([reloadChecklist(), reloadRecords(), loadOverview(), reloadLedger()])
    if (!payload.duplicate) batchSelection.value = []
  } catch (error) {
    message.value = error instanceof Error ? error.message : '批量登记失败'
  } finally {
    submitting.value = false
  }
}

async function runAction(action: string, row: Facility) {
  message.value = ''
  await singleAction(row.id, action)
}

async function replaceFacility(entryId: number, fromRejected = false) {
  await singleAction(entryId, '安排更换')
  if (fromRejected && batchResult.value?.rejected_expired) {
    batchResult.value.rejected_expired = batchResult.value.rejected_expired.filter(
      (item) => item.facility_id !== entryId,
    )
  }
}

async function singleAction(entryId: number, action: string) {
  message.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entryId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!payload.ok) throw new Error(payload.message)
    await refreshAll()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '操作失败'
  }
}

function openCreate() {
  createFields.forEach((field) => { createForm[field] = '' })
  createError.value = ''
  createOpen.value = true
}

async function submitCreate() {
  createError.value = ''
  const values: Record<string, string> = {}
  createFields.forEach((field) => { values[field] = createForm[field].trim() })
  const response = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values }) })
  const payload = await response.json()
  if (!payload.ok) { createError.value = payload.message; return }
  createOpen.value = false
  await refreshAll()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

onMounted(refreshAll)
onMounted(loadFilters)
</script>

<style scoped>
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 12px; }
.tab { border: none; background: none; padding: 8px 14px; cursor: pointer; font-size: 14px; color: var(--muted); border-bottom: 2px solid transparent; position: relative; }
.tab.active { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
.tab-badge { font-style: normal; background: #fde8e8; color: #b42318; border-radius: 10px; padding: 0 7px; font-size: 12px; margin-left: 4px; }
.hint { font-size: 12px; color: var(--muted); margin: 0 0 12px; }
.hint code, td code { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 12px; }

.stat-card.card-danger { border-color: #f0a8a0; background: #fef3f2; }
.stat-card.card-warn { border-color: #f5cf8d; background: #fffaeb; }

.group-section { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 14px; }
.group-title { margin: 0 0 10px; font-size: 15px; }
.month-block { margin-bottom: 12px; }
.month-title { margin: 8px 0 6px; font-size: 13px; color: var(--muted); font-weight: 600; }
.month-count { margin-left: 8px; font-size: 12px; }
.empty-inline { color: var(--muted); font-size: 13px; margin: 4px 0; }

.tag-cell { white-space: nowrap; }
.tag { display: inline-block; border-radius: 4px; padding: 1px 8px; font-size: 12px; margin-right: 4px; }
.tag-expired { background: #fde8e8; color: #b42318; border: 1px solid #f0a8a0; }
.tag-pressure { background: #ffedd5; color: #b45309; border: 1px solid #f5cf8d; }
.tag-soon { background: #fffaeb; color: #b45309; border: 1px solid #f5cf8d; }
.tag-ok { background: #e8f5e9; color: #1e7e34; border: 1px solid #a5d6a7; }
.tag-replaced { background: #eef0f3; color: #667085; border: 1px solid #d0d5dd; }
.expired-text { color: #b42318; }
.soon-text, .pressure-text { color: #b45309; }
.ok-text { color: #1e7e34; }
.danger-text { color: #b42318; }
.sub-text { display: block; color: var(--muted); font-size: 11px; margin-top: 2px; }
.sub-expired { color: #b42318; }
.sub-soon { color: #b45309; }
.sub-replaced { color: #667085; }

.filter-bar select { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }
.filter-item.grow { flex: 1; min-width: 220px; }

.check-col { width: 36px; text-align: center; }
.batch-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; margin-bottom: 8px; }
.batch-toolbar input { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }

.result-panel { border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-top: 14px; background: #fff; }
.result-panel.is-duplicate { border-color: #f5cf8d; background: #fffaeb; }
.result-message { margin: 4px 0 10px; font-size: 13px; }
.result-section { margin-top: 8px; }
.result-section h5 { margin: 6px 0; font-size: 13px; }
.result-list { margin: 0; padding-left: 18px; font-size: 13px; }
.result-list li { margin: 4px 0; }
.rejected-item { display: flex; justify-content: space-between; gap: 12px; align-items: center; }

.modal-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.45); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal { background: #fff; border-radius: 10px; padding: 18px 20px; width: 420px; display: flex; flex-direction: column; gap: 10px; }
.modal h3 { margin: 0 0 4px; }
.modal input { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; width: 100%; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }
</style>
