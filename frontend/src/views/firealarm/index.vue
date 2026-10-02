<template>
  <section class="page" data-module="firealarm">
    <header class="page-head">
      <div>
        <h2>消防设施管理</h2>
        <p class="page-desc">按灭火剂量与有效期分档管理；按月盯到期，批量登记检查，过期设施先更换再检查。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出台账</button>
      </div>
    </header>

    <div class="stat-row">
      <article
        v-for="item in overview.cards"
        :key="item.label"
        class="stat-card"
        :class="cardClass(item.label)"
      >
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <nav class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- 设施台账 -->
    <div v-if="activeTab === 'ledger'" class="tab-panel">
      <form class="filter-bar" @submit.prevent="reloadLedger">
        <label class="filter-item">
          <span>设施编号/类型</span>
          <input v-model="ledgerFilters.keyword" placeholder="按编号或类型检索" />
        </label>
        <label class="filter-item">
          <span>所属站点</span>
          <input v-model="ledgerFilters.site" placeholder="按站点检索" />
        </label>
        <label class="filter-item">
          <span>剂量分档</span>
          <select v-model="ledgerFilters.dose_tier">
            <option value="">全部</option>
            <option v-for="tier in doseTiers" :key="tier" :value="tier">{{ tier }}</option>
          </select>
        </label>
        <label class="filter-item">
          <span>有效期分档</span>
          <select v-model="ledgerFilters.expiry_tier">
            <option value="">全部</option>
            <option v-for="tier in expiryTiers" :key="tier" :value="tier">{{ tier }}</option>
          </select>
        </label>
        <label class="filter-item">
          <span>状态</span>
          <select v-model="ledgerFilters.status">
            <option value="">全部</option>
            <option v-for="st in statuses" :key="st" :value="st">{{ st }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetLedgerFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>设施编号</th>
            <th>设施类型</th>
            <th>所属站点</th>
            <th>灭火剂量</th>
            <th>剂量分档</th>
            <th>有效期至</th>
            <th>剩余天数</th>
            <th>压力</th>
            <th>状态</th>
            <th>上次检查</th>
            <th>检查人员</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in ledger" :key="String(row.id)" :class="rowClass(row)">
            <td>{{ row['设施编号'] }}</td>
            <td>{{ row['设施类型'] }}</td>
            <td>{{ row['所属站点'] }}</td>
            <td>{{ row['灭火剂量'] }}</td>
            <td>{{ row['灭火剂量分档'] }}</td>
            <td>{{ row['有效期至'] }}</td>
            <td>{{ daysLeftText(row) }}</td>
            <td>
              <span v-if="row['压力异常']" class="tag tag-warn">压力不足</span>
              <span v-else>正常</span>
            </td>
            <td><span class="tag" :class="statusTag(row.status)">{{ row.status }}</span></td>
            <td>{{ row['上次检查'] || '—' }}</td>
            <td>{{ row['检查人员'] || '—' }}</td>
            <td>
              <button class="link" type="button" @click="requestReplace(row)">安排更换</button>
            </td>
          </tr>
          <tr v-if="!ledger.length">
            <td colspan="12" class="empty-state">没有符合条件的消防设施</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot"><span>共 {{ ledgerTotal }} 条设施记录</span></footer>
    </div>

    <!-- 到期分档 -->
    <div v-if="activeTab === 'expiry'" class="tab-panel">
      <h3 class="block-title danger-title">已过期（{{ expiredCount }} 台，须先安排更换，不排入检查清单）</h3>
      <div v-for="bucket in overview.expired_months" :key="'e-' + bucket.month" class="month-block">
        <div class="month-head">
          <span class="tag tag-danger">{{ bucket.month }}</span>
          <span>{{ bucket.count }} 台已过期</span>
        </div>
        <table class="data-table compact">
          <thead>
            <tr><th>设施编号</th><th>设施类型</th><th>所属站点</th><th>灭火剂量</th><th>剂量分档</th><th>有效期至</th><th>压力</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in bucket.items" :key="String(row.id)" class="row-danger">
              <td>{{ row['设施编号'] }}</td>
              <td>{{ row['设施类型'] }}</td>
              <td>{{ row['所属站点'] }}</td>
              <td>{{ row['灭火剂量'] }}</td>
              <td>{{ row['灭火剂量分档'] }}</td>
              <td>{{ row['有效期至'] }}</td>
              <td>
                <span v-if="row['压力异常']" class="tag tag-warn">压力不足</span>
                <span v-else>正常</span>
              </td>
              <td><button class="link" type="button" @click="requestReplace(row)">安排更换</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!overview.expired_months.length" class="empty-state block-empty">当前没有已过期设施</p>

      <h3 class="block-title soon-title">即将到期（90 天内，按月列出）</h3>
      <div v-for="bucket in overview.expiring_months" :key="'s-' + bucket.month" class="month-block">
        <div class="month-head">
          <span class="tag tag-soon">{{ bucket.month }}</span>
          <span>{{ bucket.count }} 台到期</span>
        </div>
        <table class="data-table compact">
          <thead>
            <tr><th>设施编号</th><th>设施类型</th><th>所属站点</th><th>灭火剂量</th><th>剂量分档</th><th>有效期至</th><th>剩余天数</th><th>压力</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in bucket.items" :key="String(row.id)" :class="{ 'row-soon': withinDays(row, 30) }">
              <td>{{ row['设施编号'] }}</td>
              <td>{{ row['设施类型'] }}</td>
              <td>{{ row['所属站点'] }}</td>
              <td>{{ row['灭火剂量'] }}</td>
              <td>{{ row['灭火剂量分档'] }}</td>
              <td>{{ row['有效期至'] }}</td>
              <td>剩 {{ row['剩余天数'] }} 天</td>
              <td>
                <span v-if="row['压力异常']" class="tag tag-warn">压力不足</span>
                <span v-else>正常</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!overview.expiring_months.length" class="empty-state block-empty">90 天内没有即将到期的设施</p>

      <h3 class="block-title warn-title">压力不足（与过期分开标记，仍需检查并安排补压/更换）</h3>
      <table class="data-table compact">
        <thead>
          <tr><th>设施编号</th><th>设施类型</th><th>所属站点</th><th>灭火剂量</th><th>有效期至</th><th>剩余天数</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in overview.low_pressure" :key="String(row.id)" class="row-warn">
            <td>{{ row['设施编号'] }}</td>
            <td>{{ row['设施类型'] }}</td>
            <td>{{ row['所属站点'] }}</td>
            <td>{{ row['灭火剂量'] }}</td>
            <td>{{ row['有效期至'] }}</td>
            <td>{{ daysLeftText(row) }}</td>
          </tr>
          <tr v-if="!overview.low_pressure.length">
            <td colspan="6" class="empty-state">没有压力不足的设施</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 批量检查 -->
    <div v-if="activeTab === 'batch'" class="tab-panel">
      <div class="batch-toolbar">
        <label class="filter-item">
          <span>检查日期</span>
          <input v-model="batchForm.checkDate" type="date" />
        </label>
        <label class="filter-item">
          <span>检查人员</span>
          <input v-model="batchForm.inspector" placeholder="登记到本批每台设施" />
        </label>
        <label class="filter-item filter-grow">
          <span>备注（可选）</span>
          <input v-model="batchForm.note" placeholder="本批统一备注" />
        </label>
        <div class="batch-actions">
          <button class="btn" type="button" @click="selectAllVisible">全选本页</button>
          <button class="btn ghost" type="button" @click="clearSelection">清空勾选</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitBatch">
            {{ submitting ? '提交中…' : `批量登记检查（已选 ${selected.size} 台）` }}
          </button>
        </div>
      </div>
      <p class="batch-hint">清单已自动排除已过期设施；逐台带出上次检查日期与检查人员。过期设施请到「到期分档」先安排更换。</p>

      <table class="data-table">
        <thead>
          <tr>
            <th class="col-check"><input type="checkbox" :checked="allVisibleChecked" @change="toggleAllVisible" /></th>
            <th>设施编号</th>
            <th>所属站点</th>
            <th>设施类型</th>
            <th>灭火剂量</th>
            <th>剂量分档</th>
            <th>有效期至</th>
            <th>剩余天数</th>
            <th>压力</th>
            <th>上次检查日期</th>
            <th>上次检查人员</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in checklist" :key="String(row.id)" :class="rowClass(row)">
            <td class="col-check">
              <input type="checkbox" :value="String(row.id)" v-model="selectionModel" />
            </td>
            <td>{{ row['设施编号'] }}</td>
            <td>{{ row['所属站点'] }}</td>
            <td>{{ row['设施类型'] }}</td>
            <td>{{ row['灭火剂量'] }}</td>
            <td>{{ row['灭火剂量分档'] }}</td>
            <td>{{ row['有效期至'] }}</td>
            <td>{{ daysLeftText(row) }}</td>
            <td>
              <span v-if="row['压力异常']" class="tag tag-warn">压力不足</span>
              <span v-else>正常</span>
            </td>
            <td>{{ row['上次检查日期'] || '—' }}</td>
            <td>{{ row['上次检查人员'] || '—' }}</td>
          </tr>
          <tr v-if="!checklist.length">
            <td colspan="11" class="empty-state">暂无可排期检查的设施（已过期设施已排除）</td>
          </tr>
        </tbody>
      </table>

      <div v-if="batchResult" class="result-box" :class="batchResult.rejected.length ? 'result-warn' : 'result-ok'">
        <p>{{ batchResult.message }}</p>
        <p v-if="batchResult.duplicated" class="dup-note">同一批次重复提交，系统只记录了一次。</p>
        <ul v-if="batchResult.recorded.length">
          <li v-for="item in batchResult.recorded" :key="String(item['设施编号'])">
            ✅ {{ item['设施编号'] }}（{{ item['所属站点'] }}）已登记：{{ item['检查结果'] }}
          </li>
        </ul>
        <ul v-if="batchResult.rejected.length">
          <li v-for="item in batchResult.rejected" :key="String(item['设施编号'])">
            ↩️ {{ item['设施编号'] }}（{{ item['所属站点'] }}）有效期至 {{ item['有效期至'] }}：{{ item['原因'] }}
          </li>
        </ul>
      </div>
    </div>

    <!-- 检查记录 -->
    <div v-if="activeTab === 'records'" class="tab-panel">
      <form class="filter-bar" @submit.prevent="reloadChecks">
        <label class="filter-item">
          <span>设施编号</span>
          <input v-model="checkFacility" placeholder="按设施编号过滤" />
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="checkFacility = ''; reloadChecks()">全部记录</button>
      </form>
      <table class="data-table">
        <thead>
          <tr><th>检查日期</th><th>设施编号</th><th>检查人员</th><th>检查结果</th><th>备注</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in checkRecords" :key="String(row.id)">
            <td>{{ row['检查日期'] }}</td>
            <td>{{ row['设施编号'] }}</td>
            <td>{{ row['检查人员'] }}</td>
            <td>
              <span class="tag" :class="row['检查结果'] === '压力不足' ? 'tag-warn' : 'tag-ok'">
                {{ row['检查结果'] }}
              </span>
            </td>
            <td>{{ row['备注'] || '—' }}</td>
          </tr>
          <tr v-if="!checkRecords.length">
            <td colspan="5" class="empty-state">暂无检查记录</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot"><span>共 {{ checkTotal }} 条检查记录</span></footer>
    </div>

    <!-- 安排更换弹层 -->
    <div v-if="replaceTarget" class="modal-mask" @click.self="replaceTarget = null">
      <div class="modal">
        <h3>安排更换：{{ replaceTarget['设施编号'] }}</h3>
        <p class="modal-desc">
          {{ replaceTarget['所属站点'] }} · {{ replaceTarget['设施类型'] }} ·
          当前有效期至 {{ replaceTarget['有效期至'] }}
        </p>
        <label class="filter-item">
          <span>新有效期</span>
          <input v-model="replaceForm.newExpiry" type="date" />
        </label>
        <label class="filter-item">
          <span>经办人</span>
          <input v-model="replaceForm.inspector" placeholder="安排更换的人员" />
        </label>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="replaceTarget = null">取消</button>
          <button class="btn primary" type="button" :disabled="replaceSubmitting" @click="confirmReplace">
            {{ replaceSubmitting ? '提交中…' : '确认更换' }}
          </button>
        </div>
        <p v-if="replaceError" class="error-text">{{ replaceError }}</p>
      </div>
    </div>

    <footer class="page-foot">
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type MonthBucket = { month: string; count: number; items: Row[] }
type Overview = {
  cards: { label: string; value: number }[]
  expired_months: MonthBucket[]
  expiring_months: MonthBucket[]
  low_pressure: Row[]
}
type BatchResult = {
  ok: boolean
  duplicated: boolean
  message: string
  batch_no: string
  recorded: Row[]
  rejected: Row[]
  missing: string[]
}

const ENDPOINT = '/api/firealarm'
const tabs = [
  { key: 'ledger', label: '设施台账' },
  { key: 'expiry', label: '到期分档' },
  { key: 'batch', label: '批量检查' },
  { key: 'records', label: '检查记录' },
] as const
type TabKey = (typeof tabs)[number]['key']

const doseTiers = ['手提式', '推车式']
const expiryTiers = ['已过期', '30天内到期', '31-90天到期', '正常在用']
const statuses = ['合格', '压力不足', '已过期']

const activeTab = ref<TabKey>('ledger')
const errorMessage = ref('')

const overview = ref<Overview>({ cards: [], expired_months: [], expiring_months: [], low_pressure: [] })
const expiredCount = computed(() => overview.value.cards.find((c) => c.label === '已过期')?.value ?? 0)

// --------------------------------------------------------------- 台账
const ledger = ref<Row[]>([])
const ledgerTotal = ref(0)
const ledgerFilters = reactive({ keyword: '', site: '', dose_tier: '', expiry_tier: '', status: '' })

async function reloadLedger() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  Object.entries(ledgerFilters).forEach(([key, value]) => {
    if (value) params.set(key, value)
  })
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}&size=200`)
    if (!response.ok) throw new Error('消防设施台账读取失败')
    const payload = await response.json()
    ledger.value = payload.items ?? []
    ledgerTotal.value = payload.total ?? 0
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '消防设施台账读取失败'
  }
}

function resetLedgerFilters() {
  Object.assign(ledgerFilters, { keyword: '', site: '', dose_tier: '', expiry_tier: '', status: '' })
  void reloadLedger()
}

// --------------------------------------------------------------- 到期分档
async function reloadOverview() {
  try {
    const response = await request(`${ENDPOINT}/expiry-overview`)
    if (!response.ok) throw new Error('到期分档数据读取失败')
    overview.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '到期分档数据读取失败'
  }
}

// --------------------------------------------------------------- 批量检查
const checklist = ref<Row[]>([])
const selected = ref<Set<string>>(new Set())
const submitting = ref(false)
const batchResult = ref<BatchResult | null>(null)
// 同一批重复提交用固定批次号；成功/失败后再开新批时换新号
const batchNo = ref(makeBatchNo())
const batchForm = reactive({ checkDate: todayISO(), inspector: '', note: '' })

const selectionModel = computed<Set<string>>({
  get: () => selected.value,
  set: (next: Set<string>) => {
    selected.value = new Set(next)
  },
})

const allVisibleChecked = computed(
  () => checklist.value.length > 0 && checklist.value.every((row) => selected.value.has(String(row.id))),
)

async function reloadChecklist() {
  try {
    const response = await request(`${ENDPOINT}/checklist`)
    if (!response.ok) throw new Error('检查清单读取失败')
    const payload = await response.json()
    checklist.value = payload.items ?? []
    // 清单刷新后清掉已不存在（例如被排除）的勾选项
    const validIds = new Set(checklist.value.map((row) => String(row.id)))
    selected.value = new Set([...selected.value].filter((id) => validIds.has(id)))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检查清单读取失败'
  }
}

function selectAllVisible() {
  selected.value = new Set(checklist.value.map((row) => String(row.id)))
}

function clearSelection() {
  selected.value = new Set()
}

function toggleAllVisible(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  if (checked) selectAllVisible()
  else clearSelection()
}

async function submitBatch() {
  errorMessage.value = ''
  if (!selected.value.size) {
    errorMessage.value = '请先勾选要检查的设施'
    return
  }
  if (!batchForm.inspector.trim()) {
    errorMessage.value = '请填写检查人员'
    return
  }
  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/batch-check`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          batch_no: batchNo.value,
          检查人员: batchForm.inspector.trim(),
          检查日期: batchForm.checkDate,
          备注: batchForm.note.trim(),
          ids: [...selected.value],
        },
      }),
    })
    if (!response.ok) throw new Error('批量登记未生效，请稍后重试')
    batchResult.value = await response.json()
    // 无论整批成功还是部分退回，这批都已落账；换新批次号供下一批使用并清空勾选
    batchNo.value = makeBatchNo()
    clearSelection()
    await Promise.all([reloadChecklist(), reloadOverview(), reloadLedger(), reloadChecks()])
  } catch (error) {
    // 网络错误时保留原批次号：用户重试仍走幂等，不会重复登记
    errorMessage.value = error instanceof Error ? error.message : '批量登记失败'
  } finally {
    submitting.value = false
  }
}

// --------------------------------------------------------------- 检查记录
const checkRecords = ref<Row[]>([])
const checkTotal = ref(0)
const checkFacility = ref('')

async function reloadChecks() {
  try {
    const query = checkFacility.value.trim() ? `?facility=${encodeURIComponent(checkFacility.value.trim())}` : ''
    const response = await request(`${ENDPOINT}/checks${query}`)
    if (!response.ok) throw new Error('检查记录读取失败')
    const payload = await response.json()
    checkRecords.value = payload.items ?? []
    checkTotal.value = payload.total ?? 0
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检查记录读取失败'
  }
}

// --------------------------------------------------------------- 更换
const replaceTarget = ref<Row | null>(null)
const replaceForm = reactive({ newExpiry: '', inspector: '' })
const replaceSubmitting = ref(false)
const replaceError = ref('')

function requestReplace(row: Row) {
  replaceTarget.value = row
  replaceError.value = ''
  replaceForm.inspector = batchForm.inspector || String(row['检查人员'] ?? '')
  replaceForm.newExpiry = defaultExpiry()
}

async function confirmReplace() {
  if (!replaceTarget.value) return
  replaceError.value = ''
  replaceSubmitting.value = true
  try {
    const response = await request(`${ENDPOINT}/${replaceTarget.value.id}/replace`, {
      method: 'POST',
      body: JSON.stringify({
        values: { 新有效期: replaceForm.newExpiry, 检查人员: replaceForm.inspector.trim() },
      }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '安排更换未生效')
    }
    replaceTarget.value = null
    await Promise.all([reloadOverview(), reloadChecklist(), reloadLedger()])
  } catch (error) {
    replaceError.value = error instanceof Error ? error.message : '安排更换失败'
  } finally {
    replaceSubmitting.value = false
  }
}

// --------------------------------------------------------------- 杂项
function switchTab(key: TabKey) {
  activeTab.value = key
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function daysLeftText(row: Row): string {
  const left = row['剩余天数']
  if (typeof left !== 'number') return '—'
  if (left < 0) return '已过期'
  return `剩 ${left} 天`
}

function withinDays(row: Row, days: number): boolean {
  const left = row['剩余天数']
  return typeof left === 'number' && left >= 0 && left <= days
}

function statusTag(status: unknown): string {
  if (status === '已过期') return 'tag-danger'
  if (status === '压力不足') return 'tag-warn'
  return 'tag-ok'
}

function cardClass(label: string): string {
  if (label === '已过期') return 'card-danger'
  if (label.includes('30天内')) return 'card-soon'
  if (label === '压力不足') return 'card-warn'
  return ''
}

function rowClass(row: Row): string {
  if (row['过期标记']) return 'row-danger'
  if (row['压力异常']) return 'row-warn'
  const left = row['剩余天数']
  if (typeof left === 'number' && left >= 0 && left <= 30) return 'row-soon'
  return ''
}

function todayISO(): string {
  const now = new Date()
  const month = `${now.getMonth() + 1}`.padStart(2, '0')
  const day = `${now.getDate()}`.padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function defaultExpiry(): string {
  const now = new Date()
  return `${now.getFullYear() + 1}-${`${now.getMonth() + 1}`.padStart(2, '0')}-${`${now.getDate()}`.padStart(2, '0')}`
}

function makeBatchNo(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `BATCH-${Date.now()}-${Math.floor(Math.random() * 1e6)}`
}

onMounted(() => {
  void reloadOverview()
  void reloadLedger()
  void reloadChecklist()
  void reloadChecks()
})
</script>

<style scoped>
.tab-bar { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 12px; }
.tab-btn { border: none; background: none; padding: 8px 16px; cursor: pointer; font-size: 14px; color: var(--muted); border-bottom: 2px solid transparent; }
.tab-btn.active { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
.tab-panel { background: transparent; }

.stat-card.card-danger { border-left: 4px solid #d92d20; }
.stat-card.card-warn { border-left: 4px solid #f79009; }
.stat-card.card-soon { border-left: 4px solid #eaaa00; }

.tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; line-height: 18px; }
.tag-danger { background: #fef3f2; color: #b42318; border: 1px solid #fecdca; }
.tag-warn { background: #fffaeb; color: #b54708; border: 1px solid #fedf89; }
.tag-soon { background: #fffaeb; color: #a15c07; border: 1px solid #fec84b; }
.tag-ok { background: #ecfdf3; color: #027a48; border: 1px solid #abefc6; }

.row-danger { background: #fef6f5; }
.row-warn { background: #fffaeb; }
.row-soon { background: #fffdf5; }
.compact th, .compact td { padding: 6px 8px; }

.block-title { font-size: 14px; margin: 18px 0 8px; }
.danger-title { color: #b42318; }
.warn-title { color: #b54708; }
.soon-title { color: #a15c07; }
.month-block { margin-bottom: 12px; }
.month-head { display: flex; gap: 10px; align-items: center; margin-bottom: 4px; font-size: 13px; }
.block-empty { padding: 8px; }

.batch-toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; margin-bottom: 6px; }
.filter-grow { flex: 1; min-width: 220px; }
.batch-actions { display: flex; gap: 8px; }
.batch-hint { font-size: 12px; color: var(--muted); margin: 0 0 10px; }
.col-check { width: 36px; text-align: center; }

.result-box { margin-top: 12px; border-radius: 8px; padding: 10px 14px; font-size: 13px; }
.result-box ul { margin: 6px 0 0; padding-left: 20px; }
.result-ok { background: #ecfdf3; border: 1px solid #abefc6; }
.result-warn { background: #fffaeb; border: 1px solid #fedf89; }
.dup-note { color: #b54708; margin: 4px 0 0; }

.modal-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.45); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal { background: #fff; border-radius: 10px; padding: 20px 24px; width: 420px; box-shadow: 0 12px 40px rgba(16, 24, 40, 0.2); }
.modal h3 { margin: 0 0 4px; font-size: 16px; }
.modal-desc { color: var(--muted); font-size: 12px; margin: 0 0 12px; }
.modal .filter-item { display: block; margin-bottom: 10px; }
.modal .filter-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 2px; }
.modal .filter-item input { width: 100%; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }

.filter-bar select, .batch-toolbar select, .filter-bar input, .batch-toolbar input {
  border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-size: 13px;
}
</style>
