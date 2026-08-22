<script setup lang="ts">
import {
  Brain,
  Compass,
  Download,
  ExternalLink,
  FileText,
  History,
  LoaderCircle,
  MapPin,
  MessageCircle,
  Play,
  Plus,
  RefreshCw,
  Save,
  Send,
  Share2,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  X
} from '@lucide/vue'
import { apiUrl } from './api'
import { toPng } from 'html-to-image'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

interface Spot {
  name: string
  address: string
  duration: string
  description: string
  location: string
  booking_url?: string
  booking_label?: string
}

interface Food {
  name: string
  cuisine: string
  price_range: string
  address: string
  description: string
  best_time: string
  location: string
}

interface Hotel {
  name: string
  address: string
  location: string
  category: string
  phone: string
  price_hint: string
}

interface WeatherForecast {
  date: string
  week: string
  day_weather: string
  night_weather: string
  temp_min: number
  temp_max: number
  wind_direction: string
  wind_power: string
  precipitation_probability: number
  suggestion: string
}
interface Weather {
  city: string
  weather: string
  temperature: string
  wind_direction: string
  wind_power: string
  humidity: string
  report_time: string
  travel_date?: string
  forecasts?: WeatherForecast[]
}

interface NearbyPoi {
  name: string
  address: string
  location: string
  category: string
  distance: string
}

interface RouteInfo {
  mode: string
  duration_seconds: number
  distance_meters: number
  duration_text: string
  distance_text: string
  polyline: string
  leg_key?: string
  from_name?: string
  to_name?: string
  from_location?: string
  to_location?: string
  day?: number
  stop_type?: string
}

interface DayPlan {
  day: number
  theme: string
  spots: Spot[]
  foods: Food[]
}

interface BudgetReport {
  budget: number
  total_cost: number
  within_budget: boolean
  savings: number
  suggestions: string[]
}

interface BudgetCategoryItem {
  name: string
  amount: number
}

interface BudgetCategoryDetail {
  category: string
  amount: number
  min_amount?: number
  max_amount?: number
  typical?: number
  note?: string
  items: BudgetCategoryItem[]
}

interface BudgetDayDetail {
  day: number
  amount: number
  min_amount?: number
  max_amount?: number
  typical?: number
  categories: Record<string, number>
}

interface ActualExpense {
  day: number
  category: string
  amount: number | null
  note: string
  rowKey?: string
}

interface BudgetDetail {
  total_cost: number
  budget: number
  days: BudgetDayDetail[]
  categories: BudgetCategoryDetail[]
  actual_expenses?: ActualExpense[]
}

interface TripPlan {
  destination: string
  days: number
  budget: number
  preferences: string[]
  overview: string
  daily_plans: DayPlan[]
  total_cost: number
  notes: string[]
  budget_report: BudgetReport | null
  budget_detail?: BudgetDetail | null
  user_memory?: Record<string, unknown>
  spending_profile?: Record<string, unknown>
  quality_report?: { passed: boolean; issues: string[]; repairs?: string[]; checked_at?: string }
  hotels: Hotel[]
  weather: Weather | null
  nearby: NearbyPoi[]
  routes: Record<string, RouteInfo>
  route_legs?: RouteInfo[]
  transport_mode?: string
  variant_label?: string
  variant_pace?: string
  variant_theme?: string
}

interface HistoryItem {
  id: number
  destination: string
  days: number
  budget: number
  created_at: string
}

interface ChatSession {
  id: number
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

interface UserMemory {
  preferences: string[]
  visited_cities: string[]
  dietary_notes: string
  pace: string
  transport_mode: string
  hotel_budget: number
  companions: number
  updated_at: string
}


const destination = ref('')
const days = ref(3)
const budget = ref(3000)
const preferences = ref<string[]>(['美食', '人文'])
const loading = ref(false)
const error = ref('')
const generationFailed = ref(false)
const plan = ref<TripPlan | null>(null)
const actualExpenses = ref<ActualExpense[]>([])
const mapEl = ref<HTMLElement | null>(null)
let mapInstance: any = null
const selectedDay = ref(1)
const activeLedgerDay = ref(1)
let dayRoutes: Array<{ day: number; name: string; path: [number, number][]; fromName?: string; toName?: string; mode?: string; stopType?: string }> = []
let playMarker: any = null
const playing = ref(false)
const playSpeed = ref(1)
const routeProgress = ref('')
let routeCancel = false
const activeSpotName = ref('')
const activeSpotDay = ref(0)
let mapMarkers: Array<{ name: string; marker: any }> = []
let mapPolylines: Array<{ name: string; polyline: any; baseColor: string; baseWeight: number }> = []

const progress = ref('')
const progressStep = ref('')

const adjustMessage = ref('')
const adjusting = ref(false)
const adjustError = ref('')

const nodeLabels: Record<string, string> = {
  analyze: '需求解析中',
  attractions: '景点筛选中',
  foods: '美食筛选中',
  hotels: '酒店筛选中',
  weather: '天气查询中',
  itinerary: '行程编排中',
  budget: '预算审核中',
  quality: '质量校验中',
  surrounding: '路线与周边整理中'
}
const departureCity = ref('')
const travelDate = ref('')
const transportMode = ref('auto')
const routeRecalculating = ref(false)
const routeError = ref('')
const infoOpen = ref(false)
const chatOpen = ref(false)
const shareCardEl = ref<HTMLElement | null>(null)
const hotelBudget = ref(0)
const dietaryNotes = ref('')
const companions = ref(1)
const compareMode = ref(false)
const planVariants = ref<TripPlan[]>([])
const activeVariantIndex = ref(0)
const variantProgress = ref<{ index: number; total: number; label: string } | null>(null)


const preferenceOptions = ['美食', '人文', '自然', '亲子', '购物', '夜生活']
const compareOptions = [
  { label: '单方案', value: false },
  { label: '主题三方案', value: true }
]
const variantFallbackLabels = ['人文深度', '美食探店', '自然休闲']
const variantThemeHints: Record<string, string> = {
  '人文深度': '人文优先',
  '美食探店': '美食优先',
  '自然休闲': '自然优先',
  '亲子轻松': '亲子优先',
  '经济优选': '平价优先'
}
const paceOptions = [
  { label: '紧凑', value: 'compact' },
  { label: '标准', value: 'standard' },
  { label: '舒适', value: 'relaxed' }
]
const transportOptions = [
  { label: '自动', value: 'auto' },
  { label: '步行', value: 'walking' },
  { label: '驾车', value: 'driving' },
  { label: '公交', value: 'transit' },
  { label: '骑行', value: 'bicycling' }
]
const routeModeLabels: Record<string, string> = {
  auto: '自动',
  walking: '步行',
  driving: '驾车',
  transit: '公交',
  bicycling: '骑行'
}
const routeModeColors: Record<string, string> = {
  auto: '#1c4b40',
  walking: '#2f6f5d',
  driving: '#c56a47',
  transit: '#d99a3d',
  bicycling: '#4a7a9b'
}

const historyList = ref<HistoryItem[]>([])
const deletingHistoryId = ref<number | null>(null)
const memoryDraft = ref<UserMemory>({
  preferences: [],
  visited_cities: [],
  dietary_notes: '',
  pace: '',
  transport_mode: '',
  hotel_budget: 0,
  companions: 1,
  updated_at: ''
})
const memorySaving = ref(false)
const memoryMessage = ref('')
const newMemoryPreference = ref('')
const newVisitedCity = ref('')
const messages = ref<Array<{ role: string; content: string }>>([])
const chatInput = ref('')
const chatSending = ref(false)
const chatScrollEl = ref<HTMLElement | null>(null)
const chatSessions = ref<ChatSession[]>([])
const chatHistoryOpen = ref(false)
const chatHistoryError = ref('')
const activeChatSessionId = ref<number | null>(null)
let revealObserver: IntersectionObserver | null = null

const activeChatTitle = computed(() => {
  const active = chatSessions.value.find((item) => item.id === activeChatSessionId.value)
  return active?.title || '新对话'
})

const activeChatMessageCount = computed(() => {
  const active = chatSessions.value.find((item) => item.id === activeChatSessionId.value)
  return active?.message_count || 0
})

const progressSteps = [
  '需求解析中',
  '景点筛选中',
  '美食筛选中',
  '酒店筛选中',
  '天气查询中',
  '行程编排中',
  '预算审核中',
  '质量校验中',
  '路线与周边整理中'
]

const heroImages = [
  'https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?auto=format&fit=crop&w=1600&h=900&q=75',
  'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1600&h=900&q=75',
  'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1600&h=900&q=75',
  'https://images.unsplash.com/photo-1500835556837-99ac94a94552?auto=format&fit=crop&w=1600&h=900&q=75',
  'https://images.unsplash.com/photo-1526392060635-9d6019884377?auto=format&fit=crop&w=1600&h=900&q=75'
]
const heroImageIndex = ref(0)
let heroImageTimer: number | undefined

function rotateHeroImage() {
  heroImageIndex.value = (heroImageIndex.value + 1) % heroImages.length
}

function setHeroImage(index: number) {
  heroImageIndex.value = index
}

const heroTitle = computed(() => {
  if (plan.value) return `${plan.value.destination} ${plan.value.days} 日游`
  return destination.value ? `${destination.value} 旅行灵感` : 'AI 旅行规划助手'
})

const heroSubtitle = computed(() => {
  if (plan.value?.overview) return plan.value.overview
  return '把想去的地方、预算和偏好放在一起，生成一份可以直接出发的旅行规划。'
})

const progressPercent = computed(() => {
  if (variantProgress.value) {
    return Math.round((variantProgress.value.index / variantProgress.value.total) * 100)
  }
  if (!loading.value) return 0
  const index = progressSteps.indexOf(progressStep.value)
  if (index < 0) return 12
  return Math.round(((index + 1) / progressSteps.length) * 100)
})

const planStats = computed(() => {
  if (!plan.value) {
    return [
      { label: '目的地', value: destination.value || '待定' },
      { label: '天数', value: `${days.value} 天` },
      { label: '预算', value: `${budget.value} 元` }
    ]
  }

  const spotCount = plan.value.daily_plans.reduce((total, day) => total + day.spots.length, 0)
  return [
    { label: '总预算', value: `${plan.value.budget} 元` },
    { label: '景点', value: `${spotCount} 处` },
    { label: '花费', value: `${plan.value.total_cost || plan.value.budget} 元` }
  ]
})

function parsePrice(text: string, fallback: number) {
  const values = (text || '').match(/\d+/g)?.map(Number) ?? []
  if (!values.length) return fallback
  if (values.length >= 2) {
    return Math.round((Math.min(...values) + Math.max(...values)) / 2)
  }
  return values[0]
}

function scaleAmounts(amounts: number[], total: number) {
  const rawSum = amounts.reduce((sum, amount) => sum + Math.max(0, amount), 0)
  if (rawSum <= 0) {
    const base = Math.floor(total / amounts.length)
    return amounts.map((_, index) => base + (index < total % amounts.length ? 1 : 0))
  }

  const scaled = amounts.map((amount) =>
    Math.max(0, Math.round((Math.max(0, amount) * total) / rawSum))
  )
  let diff = total - scaled.reduce((sum, amount) => sum + amount, 0)
  let cursor = 0
  while (diff !== 0) {
    const index = cursor % scaled.length
    if (diff > 0) {
      scaled[index] += 1
    } else if (scaled[index] > 0) {
      scaled[index] -= 1
    }
    diff = total - scaled.reduce((sum, amount) => sum + amount, 0)
    cursor += 1
  }
  return scaled
}

function buildFallbackBudgetDetail(plan: TripPlan): BudgetDetail | null {
  const dayCount = plan.daily_plans.length || 1
  const total = plan.total_cost || plan.budget_report?.total_cost || plan.budget
  const base = Math.floor(total / dayCount)
  const dayDetails: Array<{ day: number; amount: number; min_amount: number; max_amount: number; typical: number; categories: Record<string, number> }> = plan.daily_plans.map((day, index) => {
    const foodCost = day.foods.reduce(
      (sum, food) => sum + parsePrice(food.price_range, 30),
      0
    )
    const ticketCost = day.spots.length * 35
    const transportCost = day.spots.length * 15 + 20
    const hotelCost = plan.hotels?.[0]
      ? parsePrice(plan.hotels[0].price_hint, Math.round((plan.budget * 0.22) / dayCount))
      : Math.round((plan.budget * 0.22) / dayCount)
    const typical = Math.round((ticketCost + foodCost + transportCost + hotelCost) / dayCount)
    return {
      day: day.day,
      amount: index === dayCount - 1 ? total - base * (dayCount - 1) : base,
      min_amount: Math.round(typical * 0.75),
      max_amount: Math.round(typical * 1.3),
      typical,
      categories: {
        门票: ticketCost,
        餐饮: foodCost,
        住宿: hotelCost,
        交通: transportCost
      }
    }
  })

  const labels = ['门票', '餐饮', '住宿', '交通']
  const categoryAmounts = labels.map((label) =>
    dayDetails.reduce((sum, day) => sum + (day.categories[label] || 0), 0)
  )
  const scaledCategories = scaleAmounts(categoryAmounts, total)
  const categories = labels.map((label, index) => ({
    category: label,
    amount: scaledCategories[index],
    min_amount: Math.round(scaledCategories[index] * 0.75),
    max_amount: Math.round(scaledCategories[index] * 1.3),
    typical: scaledCategories[index],
    items: [] as BudgetCategoryItem[]
  }))

  return {
    total_cost: total,
    budget: plan.budget,
    days: dayDetails,
    categories,
    actual_expenses: []
  }
}

const budgetDetail = computed<BudgetDetail | null>(() => {
  if (!plan.value) return null
  return plan.value.budget_detail || buildFallbackBudgetDetail(plan.value)
})

function budgetCategoryPercent(amount: number) {
  const total = budgetDetail.value?.total_cost || 0
  if (!total) return 0
  return Math.min(100, Math.round((amount / total) * 100))
}

function budgetRangeText(minAmount?: number, maxAmount?: number, typical?: number, fallback?: number) {
  const min = minAmount ?? typical ?? fallback ?? 0
  const max = maxAmount ?? typical ?? fallback ?? min
  return min === max ? `${min} 元` : `${min}-${max} 元`
}

function totalBudgetRangeText() {
  const days = budgetDetail.value?.days || []
  if (!days.length) return ''
  const min = days.reduce(
    (sum, day) => sum + (day.min_amount ?? day.typical ?? day.amount ?? 0),
    0
  )
  const max = days.reduce(
    (sum, day) => sum + (day.max_amount ?? day.typical ?? day.amount ?? min),
    0
  )
  return budgetRangeText(min, max)
}

function actualExpensesForDay(day: number) {
  return actualExpenses.value.filter((expense) => expense.day === day)
}

function setLedgerDay(day: number) {
  activeLedgerDay.value = day
}

function ledgerStackStyle(day: number): Record<string, string> {
  const distance = Math.abs(day - activeLedgerDay.value)
  const direction = day < activeLedgerDay.value ? -1 : 1
  return {
    '--stack-x': `${direction * distance * 26}px`,
    '--stack-rotate': `${direction * distance * 1.4}deg`,
    '--stack-scale': `${Math.max(0.9, 1 - distance * 0.035)}`,
    '--stack-opacity': `${Math.max(0.25, 1 - distance * 0.24)}`,
    '--stack-z': `${Math.max(0, 8 - distance * 2)}`,
  }
}

function categoryRangeText(category: string) {
  const detail = budgetDetail.value?.categories.find((item) => item.category === category)
  if (!detail) return ''
  return budgetRangeText(detail.min_amount, detail.max_amount, detail.typical, detail.amount)
}

function addDays(dateText: string, days: number) {
  const d = new Date(`${dateText}T00:00:00`)
  d.setDate(d.getDate() + days)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function forecastForDay(day: DayPlan) {
  const forecasts = plan.value?.weather?.forecasts || []
  if (!forecasts.length) return null
  const travelDate = plan.value?.weather?.travel_date
  if (travelDate) {
    const target = addDays(travelDate, day.day - 1)
    return forecasts.find((forecast) => forecast.date === target) || null
  }
  return forecasts[day.day - 1] || null
}
function ensureBudgetDetail() {
  if (!plan.value || plan.value.budget_detail) return
  const fallback = buildFallbackBudgetDetail(plan.value)
  if (fallback) plan.value.budget_detail = fallback
}

function initActualExpenses() {
  ensureBudgetDetail()
  const detail = plan.value?.budget_detail
  if (!detail) {
    actualExpenses.value = []
    return
  }

  const existing = detail.actual_expenses || []
  const rows: ActualExpense[] = []
  for (const day of detail.days) {
    for (const category of detail.categories) {
      const found = existing.find(
        (expense) => expense.day === day.day && expense.category === category.category
      )
      rows.push({
        ...(found || { day: day.day, category: category.category, amount: null, note: '' }),
        rowKey: `d${day.day}-${category.category}`
      })
    }
    for (const expense of existing) {
      const known = detail.categories.some((category) => category.category === expense.category)
      if (!known && expense.day === day.day) {
        rows.push({
          ...expense,
          rowKey: `d${day.day}-${expense.category}-custom-${rows.length}`
        })
      }
    }
  }
  actualExpenses.value = rows
}

const customExpenseOptions = ['纪念品', '特产', '小吃', '拍照', '演出', '其他']

function isCustomCategory(category: string) {
  if (!category) return true
  return !budgetDetail.value?.categories.some((item) => item.category === category)
}

function addExpense(day: number, category = '') {
  actualExpenses.value.push({
    day,
    category,
    amount: null,
    note: '',
    rowKey: `custom-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  })
}

function removeExpense(rowKey: string) {
  actualExpenses.value = actualExpenses.value.filter((expense) => expense.rowKey !== rowKey)
}

function syncActualExpensesToPlan() {
  if (!plan.value?.budget_detail) return
  plan.value.budget_detail.actual_expenses = actualExpenses.value
    .filter(
      (expense) => expense.category.trim() || expense.amount != null || expense.note.trim()
    )
    .map((expense) => {
      const { rowKey, ...rest } = expense
      return rest
    })
}

const actualTotal = computed(() =>
  actualExpenses.value.reduce((sum, expense) => sum + (Number(expense.amount) || 0), 0)
)

const budgetComparison = computed(() => {
  const days = budgetDetail.value?.days || []
  const min = days.reduce(
    (sum, day) => sum + (day.min_amount ?? day.typical ?? day.amount ?? 0),
    0
  )
  const typical = days.reduce(
    (sum, day) => sum + (day.typical ?? day.amount ?? 0),
    0
  )
  const max = days.reduce(
    (sum, day) => sum + (day.max_amount ?? day.typical ?? day.amount ?? min),
    0
  )
  const actual = actualTotal.value
  let label = '记录实际花费后自动对比'
  let tone = 'neutral'
  if (actual > 0) {
    if (actual < min) {
      label = `低于预计下限 ${min - actual} 元`
      tone = 'under'
    } else if (actual > max) {
      label = `超出预计上限 ${actual - max} 元`
      tone = 'over'
    } else {
      const diff = Math.abs(actual - typical)
      label = `在预计区间内 · 与参考差 ${diff} 元`
      tone = 'ok'
    }
  }
  return { min, max, typical, actual, label, tone }
})

const budgetScale = computed(() => {
  const budget = budgetDetail.value?.budget || budgetComparison.value.max
  const scaleMax = Math.max(budget, budgetComparison.value.max * 1.2, 1)
  const pct = (value: number) =>
    Math.min(100, Math.max(0, Math.round((value / scaleMax) * 100)))
  return {
    minPct: pct(budgetComparison.value.min),
    maxPct: pct(budgetComparison.value.max),
    actualPct: pct(budgetComparison.value.actual),
    budget
  }
})

const activeDay = computed(() => {
  if (!plan.value) return null
  return plan.value.daily_plans.find((day) => day.day === selectedDay.value) || plan.value.daily_plans[0]
})

const activeRouteModes = computed(() => {
  if (!plan.value?.route_legs?.length) return []
  const modes = new Set(
    plan.value.route_legs
      .filter((leg) => leg.day === selectedDay.value)
      .map((leg) => leg.mode || 'auto')
  )
  return (Object.keys(routeModeLabels) as string[]).filter((mode) => modes.has(mode))
})

function togglePreference(value: string) {
  const index = preferences.value.indexOf(value)
  if (index >= 0) {
    preferences.value.splice(index, 1)
  } else {
    preferences.value.push(value)
  }
}

async function loadAmapScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if ((window as any).AMap) {
      resolve()
      return
    }

    const env = (import.meta as any).env
    ;(window as any)._AMapSecurityConfig = {
      securityJsCode: env.VITE_AMAP_SECURITY_CODE
    }

    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${env.VITE_AMAP_JS_KEY}`
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('高德地图加载失败'))
    document.head.appendChild(script)
  })
}

async function renderMap() {
  if (!plan.value || !mapEl.value) return

  try {
    await loadAmapScript()

    if (mapInstance) {
      mapInstance.destroy()
      dayRoutes = []
      playMarker = null
      mapMarkers = []
      mapPolylines = []
      mapInstance = null
    }

    const AMap = (window as any).AMap
    const points: Array<{ name: string; location: string; type: string; day: number }> = []

    for (const day of plan.value.daily_plans) {
      for (const spot of day.spots) {
        if (spot.location) {
          points.push({ name: spot.name, location: spot.location, type: 'spot', day: day.day })
        }
      }
      for (const food of day.foods) {
        if (food.location) {
          points.push({ name: food.name, location: food.location, type: 'food', day: day.day })
        }
      }
    }

    if (plan.value.hotels && plan.value.hotels.length) {
      const hotel = plan.value.hotels[0]
      if (hotel.location) {
        points.push({ name: hotel.name, location: hotel.location, type: 'hotel', day: 0 })
      }
    }

    if (!points.length) return

    const visiblePoints = points.filter((point) => point.day === 0 || point.day === selectedDay.value)
    if (!visiblePoints.length) return

    const [lng, lat] = visiblePoints[0].location.split(',').map(Number)
    mapInstance = new AMap.Map(mapEl.value, {
      zoom: 12,
      center: [lng, lat]
    })

    for (const point of visiblePoints) {
      const [x, y] = point.location.split(',').map(Number)
      const marker = new AMap.Marker({
        position: [x, y],
        title: point.name,
        label: {
          content: point.name,
          direction: 'top'
        }
      })

      marker.on('click', () => {
        new AMap.InfoWindow({
          content: `<div><strong>${point.name}</strong><br/><span>${
            point.type === 'spot' ? '景点' : point.type === 'hotel' ? '酒店' : '美食'
          }</span></div>`
        }).open(mapInstance, [x, y])
      })

      mapInstance.add(marker)
      mapMarkers.push({ name: point.name, marker })
    }

    for (const day of plan.value.daily_plans) {
      if (day.day !== selectedDay.value) continue
      const legs = getRouteLegsForDay(day)
      for (const leg of legs) {
        let path: [number, number][] = []

        if (leg.polyline) {
          path = leg.polyline
            .split(';')
            .map((point) => point.split(',').map(Number)) as [number, number][]
        } else if (leg.from_location && leg.to_location && leg.from_location !== leg.to_location) {
          path = interpolatePoints(leg.from_location, leg.to_location)
        }

        if (!path.length) continue
        const mode = leg.mode || 'auto'
        const polyline = new AMap.Polyline({
          path,
          strokeColor: routeModeColors[mode] || '#1c4b40',
          strokeWeight: 4,
          strokeOpacity: 0.8,
          strokeStyle: mode === 'transit' ? 'dashed' : 'solid'
        })

        mapInstance.add(polyline)
        mapPolylines.push({
          name: leg.to_name || '',
          polyline,
          baseColor: routeModeColors[mode] || '#1c4b40',
          baseWeight: 4
        })
        dayRoutes.push({
          day: day.day,
          name: leg.to_name || leg.to_location || '下一站',
          path,
          fromName: leg.from_name,
          toName: leg.to_name,
          mode: leg.mode,
          stopType: leg.stop_type
        })
      }
    }

    mapInstance.setFitView()
    if (activeSpotName.value) {
      applySpotHighlight(activeSpotName.value)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '地图加载失败'
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function interpolatePoints(origin: string, destination: string, count = 24): [number, number][] {
  const [x1, y1] = origin.split(',').map(Number)
  const [x2, y2] = destination.split(',').map(Number)
  return Array.from({ length: count + 1 }, (_, i) => [
    x1 + ((x2 - x1) * i) / count,
    y1 + ((y2 - y1) * i) / count
  ]) as [number, number][]
}

function applySpotHighlight(name: string) {
  if (!mapInstance) return
  let target: any = null

  for (const item of mapMarkers) {
    const isActive = item.name === name
    item.marker.setLabel({
      content: isActive ? `★ ${item.name}` : item.name,
      direction: 'top'
    })
    if (typeof item.marker.setTop === 'function') {
      item.marker.setTop(isActive)
    }
    if (isActive) target = item.marker
  }

  for (const item of mapPolylines) {
    const isActive = item.name === name
    item.polyline.setOptions({
      strokeWeight: isActive ? 7 : item.baseWeight,
      strokeColor: isActive ? '#a84d38' : item.baseColor,
      strokeOpacity: isActive ? 1 : 0.8
    })
  }

  if (target) mapInstance.setCenter(target.getPosition())
}

async function focusSpot(name: string, day: number) {
  if (playing.value) return
  if (day !== selectedDay.value) {
    await selectDay(day)
  }
  activeSpotName.value = name
  activeSpotDay.value = day
  await nextTick()
  if (!mapInstance) {
    await renderMap()
    return
  }
  applySpotHighlight(name)
}

function stopRoutes() {
  routeCancel = true
  playing.value = false
  routeProgress.value = ''
}

function setPlaySpeed(speed: number) {
  playSpeed.value = speed
}

async function playRoutes() {
  if (playing.value) return
  if (!mapInstance) {
    routeProgress.value = '地图尚未加载完成，请稍后再试'
    return
  }
  if (!dayRoutes.length) {
    routeProgress.value = '当前没有可播放的路线数据'
    return
  }

  try {
    playing.value = true
    routeProgress.value = ''
    routeCancel = false
    const AMap = (window as any).AMap
    const firstPoint = dayRoutes[0].path[0]

    playMarker = new AMap.Marker({
      position: firstPoint,
      label: { content: '出发', direction: 'top' }
    })
    mapInstance.add(playMarker)

    for (const item of dayRoutes) {
      const mode = routeModeLabels[item.mode || 'auto'] || ''
      routeProgress.value = item.fromName && item.toName
        ? `${item.fromName} → ${item.toName}${mode ? ` · ${mode}` : ''}`
        : `前往 ${item.name}`
      const playPath = samplePathForPlayback(
        item.path,
        playSpeed.value >= 4 ? 40 : playSpeed.value >= 2 ? 60 : 80
      )
      for (const point of playPath) {
        if (routeCancel) break
        playMarker.setPosition(point)
        await sleep(Math.max(5, Math.round(20 / playSpeed.value)))
      }
      if (routeCancel) break
    }
  } catch (err) {
    console.error('playRoutes error', err)
  } finally {
    if (playMarker) {
      mapInstance.remove(playMarker)
      playMarker = null
    }
    playing.value = false
    routeProgress.value = ''
  }
}

async function selectDay(day: number) {
  if (playing.value || day === selectedDay.value) return
  routeCancel = true
  selectedDay.value = day
  activeSpotName.value = ''
  activeSpotDay.value = 0
  await nextTick()
  await renderMap()
}

function getRouteLegsForDay(day: DayPlan): RouteInfo[] {
  const legs = (plan.value?.route_legs || []).filter((leg) => leg.day === day.day)
  if (legs.length) return legs

  const hotel = plan.value?.hotels?.[0]
  const stops: Array<{ name: string; location: string; type: string }> = []
  const maxLength = Math.max(day.spots.length, day.foods.length)
  for (let i = 0; i < maxLength; i++) {
    const spot = day.spots[i]
    if (spot?.location) stops.push({ name: spot.name, location: spot.location, type: 'spot' })
    const food = day.foods[i]
    if (food?.location) stops.push({ name: food.name, location: food.location, type: 'food' })
  }
  if (!stops.length) return []

  let anchorName = hotel?.name || '酒店'
  let anchorLocation = hotel?.location || ''
  if (!anchorLocation) {
    anchorName = stops[0].name
    anchorLocation = stops[0].location
    stops.shift()
  }
  if (!stops.length) return []

  const synthesized: RouteInfo[] = []
  let previousName = anchorName
  let previousLocation = anchorLocation

  for (const stop of stops) {
    synthesized.push({
      mode: 'auto',
      duration_seconds: 0,
      distance_meters: 0,
      duration_text: '',
      distance_text: '',
      polyline: '',
      leg_key: `d${day.day}:${previousName}->${stop.name}`,
      from_name: previousName,
      to_name: stop.name,
      from_location: previousLocation,
      to_location: stop.location,
      day: day.day,
      stop_type: stop.type
    })
    previousName = stop.name
    previousLocation = stop.location
  }

  synthesized.push({
    mode: 'auto',
    duration_seconds: 0,
    distance_meters: 0,
    duration_text: '',
    distance_text: '',
    polyline: '',
    leg_key: `d${day.day}:${previousName}->${anchorName}`,
    from_name: previousName,
    to_name: anchorName,
    from_location: previousLocation,
    to_location: anchorLocation,
    day: day.day,
    stop_type: hotel ? 'hotel' : 'return'
  })

  return synthesized
}

function routeForSpot(name: string, day: number): RouteInfo | undefined {
  const leg = (plan.value?.route_legs || []).find(
    (route) => route.day === day && route.to_name === name && route.stop_type !== 'hotel' && route.stop_type !== 'return'
  )
  if (leg) return leg
  const legacy = plan.value?.routes && plan.value.routes[name]
  if (legacy && legacy.stop_type !== 'hotel' && legacy.stop_type !== 'return') return legacy
  return undefined
}

function samplePathForPlayback(path: [number, number][], maxPoints = 80): [number, number][] {
  if (path.length <= maxPoints) return path
  const step = (path.length - 1) / (maxPoints - 1)
  const sampled: [number, number][] = []
  for (let i = 0; i < maxPoints; i++) {
    sampled.push(path[Math.round(i * step)])
  }
  sampled[sampled.length - 1] = path[path.length - 1]
  return sampled
}

function formatRoute(spotName: string, day: number) {
  const route = routeForSpot(spotName, day)
  if (!route) return ''
  const mode = routeModeLabels[route.mode || 'auto'] || route.mode || '自动'
  const from = route.from_name || '酒店'
  if (route.duration_text) {
    return `${from} → ${spotName} · ${mode} · ${route.duration_text} · ${route.distance_text}`
  }
  return `${from} → ${spotName} · ${mode}`
}

function tripRequestBody() {
  return {
    destination: destination.value,
    days: Number(days.value),
    budget: Number(budget.value),
    preferences: preferences.value,
    departure_city: departureCity.value,
    travel_date: travelDate.value,
    hotel_budget: Number(hotelBudget.value) || 0,
    dietary_notes: dietaryNotes.value,
    companions: Number(companions.value) || 1,
    transport_mode: transportMode.value
  }
}

function variantFallbackLabel(index: number) {
  return variantFallbackLabels[index] || `方案 ${index + 1}`
}

function variantSpotCount(variant: TripPlan) {
  return variant.daily_plans.reduce((total, day) => total + day.spots.length, 0)
}

function variantPaceHint(variant: TripPlan) {
  const paceHints: Record<string, string> = {
    compact: '节奏紧凑',
    standard: '节奏均衡',
    relaxed: '节奏舒缓'
  }
  const themeHint = variantThemeHints[variant.variant_theme || variant.variant_label || ''] || '主题方案'
  const paceHint = paceHints[variant.variant_pace || ''] || '节奏适中'
  return `${themeHint} · ${paceHint}`
}

function syncActiveVariant() {
  if (!plan.value) return
  if (activeVariantIndex.value >= 0 && activeVariantIndex.value < planVariants.value.length) {
    planVariants.value[activeVariantIndex.value] = plan.value
  }
}

function submitPlan() {
  const target = destination.value.trim()
  if (!target) {
    error.value = '请先填写目的地'
    generationFailed.value = false
    return
  }
  destination.value = target
  error.value = ''
  if (compareMode.value) {
    return generateVariants()
  }
  return generatePlan()
}

function retryGeneration() {
  error.value = ''
  if (compareMode.value) {
    return generateVariants()
  }
  return generatePlan()
}

async function generatePlan() {
  loading.value = true
  error.value = ''
  generationFailed.value = false
  plan.value = null
  planVariants.value = []
  activeVariantIndex.value = 0
  variantProgress.value = null
  activeSpotName.value = ''
  activeSpotDay.value = 0
  playSpeed.value = 1
  progress.value = ''
  progressStep.value = ''
  try {
    const response = await fetch(apiUrl('/api/trip/plan/stream'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(tripRequestBody())
    })
    if (!response.ok || !response.body) {
      throw new Error(`请求失败：${response.status}`)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finished = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() ?? ''

      for (const chunk of chunks) {
        const lines = chunk.split('\n')
        const eventLine = lines.find((line) => line.startsWith('event:'))
        const dataLine = lines.find((line) => line.startsWith('data:'))

        if (!eventLine || !dataLine) continue

        const event = eventLine.slice(6).trim()
        const data = dataLine.slice(5).trim()

        if (event === 'node') {
          const payload = JSON.parse(data)
          progress.value = nodeLabels[payload.node] || payload.node
          progressStep.value = progress.value
        } else if (event === 'progress') {
          const payload = JSON.parse(data)
          progress.value = payload.message || progress.value
        } else if (event === 'done') {
          plan.value = JSON.parse(data)
          progress.value = ''
          progressStep.value = ''
          finished = true
        } else if (event === 'error') {
          const payload = JSON.parse(data)
          error.value = payload.message || '生成失败，请稍后重试'
          generationFailed.value = true
          progress.value = ''
          variantProgress.value = null
          finished = true
        }
      }

      if (finished) break
    }

    if (!plan.value && !error.value) {
      error.value = '生成失败：服务未返回行程，请稍后重试'
      generationFailed.value = true
      progress.value = ''
    }
    if (plan.value) {
      selectedDay.value = 1
      transportMode.value = plan.value.transport_mode || 'auto'
      await nextTick()
      await renderMap()
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '生成失败，请稍后重试'
    generationFailed.value = true
  } finally {
    loading.value = false
  }
}

async function generateVariants() {
  loading.value = true
  error.value = ''
  generationFailed.value = false
  plan.value = null
  planVariants.value = []
  activeVariantIndex.value = 0
  variantProgress.value = { index: 0, total: 3, label: '主题方案' }
  activeSpotName.value = ''
  activeSpotDay.value = 0
  playSpeed.value = 1
  progress.value = ''
  progressStep.value = ''
  try {
    const response = await fetch(apiUrl('/api/trip/plan/variants/stream'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(tripRequestBody())
    })
    if (!response.ok || !response.body) {
      throw new Error(`请求失败：${response.status}`)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finished = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() ?? ''

      for (const chunk of chunks) {
        const lines = chunk.split('\n')
        const eventLine = lines.find((line) => line.startsWith('event:'))
        const dataLine = lines.find((line) => line.startsWith('data:'))

        if (!eventLine || !dataLine) continue

        const event = eventLine.slice(6).trim()
        const data = dataLine.slice(5).trim()

        if (event === 'variant-start') {
          const payload = JSON.parse(data)
          const themeLabel = payload.label || payload.theme || '主题方案'
          progressStep.value = ''
          variantProgress.value = { index: payload.index, total: payload.total, label: themeLabel }
          progress.value = `正在生成 ${themeLabel} 方案（${payload.index + 1}/${payload.total}）`
        } else if (event === 'progress') {
          const payload = JSON.parse(data)
          progress.value = payload.message || progress.value
        } else if (event === 'variant-done') {
          planVariants.value.push(JSON.parse(data))
          const count = planVariants.value.length
          if (variantProgress.value) {
            variantProgress.value.index = count
          }
          const total = variantProgress.value?.total || count
          progress.value = `已生成 ${count}/${total} 套方案`
        } else if (event === 'done') {
          progress.value = ''
          variantProgress.value = null
          finished = true
        } else if (event === 'error') {
          const payload = JSON.parse(data)
          error.value = payload.message || '生成失败，请稍后重试'
          generationFailed.value = true
          progress.value = ''
          variantProgress.value = null
          finished = true
        }
      }

      if (finished) break
    }

    if (!planVariants.value.length && !error.value) {
      error.value = '生成失败：服务未返回行程，请稍后重试'
      generationFailed.value = true
      progress.value = ''
    }
    if (planVariants.value.length) {
      activeVariantIndex.value = 0
      plan.value = planVariants.value[0]
      selectedDay.value = 1
      transportMode.value = plan.value.transport_mode || 'auto'
      await nextTick()
      await renderMap()
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '生成失败，请稍后重试'
    generationFailed.value = true
  } finally {
    loading.value = false
  }
}

async function selectVariant(index: number) {
  if (index < 0 || index >= planVariants.value.length || index === activeVariantIndex.value) return
  routeCancel = true
  playing.value = false
  activeVariantIndex.value = index
  plan.value = planVariants.value[index]
  selectedDay.value = 1
  routeProgress.value = ''
  activeSpotName.value = ''
  activeSpotDay.value = 0
  playSpeed.value = 1
  transportMode.value = plan.value.transport_mode || 'auto'
  await nextTick()
  await renderMap()
}



function pushAssistant(text: string) {
  messages.value.push({ role: 'assistant', content: text })
}

function scrollChatToEnd() {
  nextTick(() => {
    if (chatScrollEl.value) {
      chatScrollEl.value.scrollTop = chatScrollEl.value.scrollHeight
    }
  })
}

function observeReveals() {
  nextTick(() => {
    const items = Array.from(document.querySelectorAll<HTMLElement>('.reveal'))
    if (!items.length) return
    if (!('IntersectionObserver' in window)) {
      items.forEach((item) => item.classList.add('in-view'))
      return
    }
    revealObserver?.disconnect()
    revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('in-view')
            revealObserver?.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.08, rootMargin: '0px 0px -12px 0px' }
    )
    items.forEach((item) => revealObserver?.observe(item))
  })
}

function handleHeroParallax() {
  const hero = document.querySelector<HTMLElement>('.hero-bg')
  if (!hero || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const offset = Math.min(window.scrollY, 320)
  hero.style.setProperty('--parallax-y', `${Math.round(offset * 0.08)}px`)
}

watch(messages, () => scrollChatToEnd())
watch(chatSending, (active) => {
  if (active) scrollChatToEnd()
})
watch(plan, () => {
  activeLedgerDay.value = 1
  initActualExpenses()
  observeReveals()
})

async function sendMessage() {
  const content = chatInput.value.trim()
  if (!content || chatSending.value) return

  messages.value.push({ role: 'user', content })
  chatInput.value = ''
  chatSending.value = true
  scrollChatToEnd()

  try {
    const response = await fetch(apiUrl('/api/chat'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: messages.value, session_id: activeChatSessionId.value })
    })
    if (!response.ok) {
      throw new Error(`请求失败：${response.status}`)
    }

    const result = await response.json()
    const sessionId = Number(result.session_id) || null
    if (sessionId) {
      activeChatSessionId.value = sessionId
      localStorage.setItem('activeChatSessionId', String(sessionId))
    }
    pushAssistant(result.reply)
    await loadChatSessions()

    if (result.ready && result.trip_request) {
      const req = result.trip_request

      destination.value = req.destination || ''
      days.value = Number(req.days) || 3
      budget.value = Number(req.budget) || 3000
      preferences.value = req.preferences || []

      departureCity.value = req.departure_city || ''
      travelDate.value = req.travel_date || ''
      hotelBudget.value = Number(req.hotel_budget) || 0
      dietaryNotes.value = req.dietary_notes || ''
      companions.value = Number(req.companions) || 1
      transportMode.value = req.transport_mode || 'auto'

      await generatePlan()
    }
  } catch (e) {
    pushAssistant(e instanceof Error ? e.message : '对话失败，请稍后重试')
  } finally {
    chatSending.value = false
  }
}

function resetToNewChat() {
  messages.value = []
  activeChatSessionId.value = null
  chatHistoryOpen.value = false
  localStorage.removeItem('activeChatSessionId')
  pushAssistant('你好，我是你的旅行规划助手。你想去哪里玩？')
}

function startNewChat() {
  if (messages.value.length > 1 && !window.confirm('开始新对话？当前会话会保留在历史中。')) return
  resetToNewChat()
}

async function loadChatSessions() {
  try {
    const response = await fetch(apiUrl('/api/chat/sessions'))
    if (!response.ok) {
      throw new Error(`加载失败：${response.status}`)
    }
    chatSessions.value = await response.json()
    chatHistoryError.value = ''
  } catch (e) {
    chatHistoryError.value = e instanceof Error ? e.message : '历史对话加载失败'
  }
}

async function loadChatSession(id: number) {
  try {
    const response = await fetch(apiUrl(`/api/chat/sessions/${id}`))
    if (!response.ok) {
      throw new Error(`加载失败：${response.status}`)
    }
    const session = await response.json()
    messages.value = session.messages || []
    activeChatSessionId.value = Number(session.id) || null
    if (activeChatSessionId.value) {
      localStorage.setItem('activeChatSessionId', String(activeChatSessionId.value))
    }
    chatHistoryOpen.value = false
    chatHistoryError.value = ''
    chatOpen.value = true
    scrollChatToEnd()
  } catch (e) {
    chatHistoryError.value = e instanceof Error ? e.message : '历史对话加载失败'
  }
}

async function deleteChatSession(id: number) {
  if (!window.confirm('确定删除这段历史对话吗？删除后无法恢复。')) return
  try {
    const response = await fetch(apiUrl(`/api/chat/sessions/${id}`), {
      method: 'DELETE'
    })
    if (!response.ok) {
      throw new Error(`删除失败：${response.status}`)
    }
    if (activeChatSessionId.value === id) {
      resetToNewChat()
    }
    await loadChatSessions()
  } catch (e) {
    chatHistoryError.value = e instanceof Error ? e.message : '历史对话删除失败'
  }
}

async function restoreActiveChat() {
  const storedId = Number(localStorage.getItem('activeChatSessionId') || '0')
  if (Number.isInteger(storedId) && storedId > 0) {
    await loadChatSession(storedId)
  }
  if (!messages.value.length) {
    pushAssistant('你好，我是你的旅行规划助手。你想去哪里玩？')
  }
  await loadChatSessions()
}


function normalizeMemory(memory: any): UserMemory {
  return {
    preferences: Array.isArray(memory?.preferences) ? memory.preferences : [],
    visited_cities: Array.isArray(memory?.visited_cities) ? memory.visited_cities : [],
    dietary_notes: memory?.dietary_notes || '',
    pace: memory?.pace || '',
    transport_mode: memory?.transport_mode || '',
    hotel_budget: Number(memory?.hotel_budget) || 0,
    companions: Number(memory?.companions) || 1,
    updated_at: memory?.updated_at || ''
  }
}

function applyMemoryToForm(memory: UserMemory) {
  for (const item of memory.preferences) {
    if (item && !preferences.value.includes(item)) preferences.value.push(item)
  }
  if (!dietaryNotes.value && memory.dietary_notes) dietaryNotes.value = memory.dietary_notes
  if (!hotelBudget.value && memory.hotel_budget) hotelBudget.value = memory.hotel_budget
  if (companions.value <= 1 && memory.companions > 1) companions.value = memory.companions
  if ((!transportMode.value || transportMode.value === 'auto') && memory.transport_mode) transportMode.value = memory.transport_mode
}

async function loadMemory() {
  try {
    const response = await fetch(apiUrl('/api/memory'))
    if (!response.ok) {
      throw new Error(`请求失败：${response.status}`)
    }
    memoryDraft.value = normalizeMemory(await response.json())
    applyMemoryToForm(memoryDraft.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '用户记忆加载失败'
  }
}

async function saveMemory() {
  if (memorySaving.value) return
  memorySaving.value = true
  memoryMessage.value = ''
  try {
    const response = await fetch(apiUrl('/api/memory'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        preferences: memoryDraft.value.preferences,
        visited_cities: memoryDraft.value.visited_cities,
        dietary_notes: memoryDraft.value.dietary_notes,
        pace: memoryDraft.value.pace,
        transport_mode: memoryDraft.value.transport_mode,
        hotel_budget: Number(memoryDraft.value.hotel_budget) || 0,
        companions: Number(memoryDraft.value.companions) || 1
      })
    })
    if (!response.ok) {
      throw new Error(`保存失败：${response.status}`)
    }
    memoryDraft.value = normalizeMemory(await response.json())
    applyMemoryToForm(memoryDraft.value)
    memoryMessage.value = '记忆已更新'
  } catch (e) {
    memoryMessage.value = e instanceof Error ? e.message : '记忆保存失败'
  } finally {
    memorySaving.value = false
    window.setTimeout(() => {
      memoryMessage.value = ''
    }, 3000)
  }
}

function toggleMemoryPreference(value: string) {
  const index = memoryDraft.value.preferences.indexOf(value)
  if (index >= 0) memoryDraft.value.preferences.splice(index, 1)
  else memoryDraft.value.preferences.push(value)
}

function addMemoryPreference() {
  const value = newMemoryPreference.value.trim()
  if (!value) return
  if (!memoryDraft.value.preferences.includes(value)) memoryDraft.value.preferences.push(value)
  newMemoryPreference.value = ''
}

function removeMemoryPreference(index: number) {
  memoryDraft.value.preferences.splice(index, 1)
}

function addVisitedCity() {
  const value = newVisitedCity.value.trim()
  if (!value) return
  if (!memoryDraft.value.visited_cities.includes(value)) memoryDraft.value.visited_cities.push(value)
  newVisitedCity.value = ''
}

function removeVisitedCity(index: number) {
  memoryDraft.value.visited_cities.splice(index, 1)
}

async function loadHistory() {
  try {
    const response = await fetch(apiUrl('/api/history'))
    if (!response.ok) {
      throw new Error(`请求失败：${response.status}`)
    }
    historyList.value = await response.json()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '历史记录加载失败'
  }
}

async function saveCurrentPlan() {
  if (!plan.value) return
  syncActualExpensesToPlan()

  try {
    const response = await fetch(apiUrl('/api/history'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan: plan.value })
    })
    if (!response.ok) {
      throw new Error(`保存失败：${response.status}`)
    }
    await loadHistory()
    await loadMemory()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败，请稍后重试'
  }
}

const savingExpenses = ref(false)
const expenseSaveMessage = ref('')

async function saveExpenses() {
  if (!plan.value || savingExpenses.value) return
  savingExpenses.value = true
  expenseSaveMessage.value = ''
  try {
    await saveCurrentPlan()
    expenseSaveMessage.value = error.value ? '保存失败，请重试' : '记账已保存，已同步到历史行程'
  } finally {
    savingExpenses.value = false
    window.setTimeout(() => {
      expenseSaveMessage.value = ''
    }, 3000)
  }
}

async function deleteHistoryItem(id: number) {
  if (!window.confirm('确定删除这条历史行程吗？删除后无法恢复。')) return
  deletingHistoryId.value = id
  try {
    const response = await fetch(apiUrl(`/api/history/${id}`), {
      method: 'DELETE'
    })
    if (!response.ok) {
      throw new Error(`删除失败：${response.status}`)
    }
    await loadHistory()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '历史行程删除失败'
  } finally {
    deletingHistoryId.value = null
  }
}
function exportMarkdown() {
  if (!plan.value) return
  syncActualExpensesToPlan()
  const p = plan.value
  const lines = [
    `# ${p.destination} ${p.days} 日游`,
    '',
    p.overview || '',
    '',
    '## 行程',
    ...p.daily_plans.flatMap((day) => [
      `### 第 ${day.day} 天 · ${day.theme}`,
      ...day.spots.map((s) => `- ${s.name}（${s.duration}）${s.description ? '：' + s.description : ''}`),
      ...(day.foods || []).map((f) => `- 美食：${f.name} · ${f.cuisine} ${f.price_range}`)
    ]),
    '',
    '## 酒店',
    ...(p.hotels || []).map((h) => `- ${h.name}：${h.address}`),
    '',
    '## 预算',
    `- ${p.budget_report?.within_budget ? '预算内' : '超出预算'} · 总花费 ${p.budget_report?.total_cost || p.budget} 元`,
    '',
    '## 实际花费',
    ...(actualExpenses.value
      .filter((expense) => expense.amount != null && Number(expense.amount) > 0)
      .map(
        (expense) =>
          `- 第 ${expense.day} 天 ${expense.category}：${expense.amount} 元${expense.note ? `（${expense.note}）` : ''}`
      ) || ['- 尚未记录']),
    '',
    '## 注意事项',
    ...(p.notes || []).map((n) => `- ${n}`)
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${p.destination}${p.days}日游.md`
  a.click()
  URL.revokeObjectURL(url)
}

function exportPdf() {
  window.print()
}

async function exportShareImage() {
  if (!plan.value || !shareCardEl.value) return
  const dataUrl = await toPng(shareCardEl.value, { pixelRatio: 2, backgroundColor: '#f6efe2' })
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = `${plan.value.destination}${plan.value.days}日游.png`
  a.click()
}


async function loadPlanFromHistory(id: number) {
  try {
    const response = await fetch(apiUrl(`/api/history/${id}`))
    if (!response.ok) {
      throw new Error(`请求失败：${response.status}`)
    }

    const loadedPlan = await response.json()
    plan.value = loadedPlan
    planVariants.value = []
    activeVariantIndex.value = 0
    variantProgress.value = null
    activeSpotName.value = ''
    activeSpotDay.value = 0
    playSpeed.value = 1
    adjustMessage.value = ''
    selectedDay.value = 1
    transportMode.value = loadedPlan.transport_mode || 'auto'

    await nextTick()
    await renderMap()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '历史行程加载失败'
  }
}

async function changeTransport(mode: string) {
  transportMode.value = mode
  if (!plan.value) return
  routeRecalculating.value = true
  routeError.value = ''
  try {
    const response = await fetch(apiUrl('/api/trip/plan/routes'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan: plan.value, transport_mode: mode })
    })
    if (!response.ok) {
      throw new Error(`路线重算失败：${response.status}`)
    }
    const updatedPlan = await response.json()
    plan.value = updatedPlan
    syncActiveVariant()
    transportMode.value = updatedPlan.transport_mode || mode
    await nextTick()
    await renderMap()
  } catch (e) {
    routeError.value = e instanceof Error ? e.message : '路线重算失败，请稍后重试'
  } finally {
    routeRecalculating.value = false
  }
}

onMounted(() => {
  void restoreActiveChat()
  loadHistory()
  loadMemory()
  observeReveals()
  window.addEventListener('scroll', handleHeroParallax, { passive: true })
  heroImageTimer = window.setInterval(rotateHeroImage, 8000)
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleHeroParallax)
  revealObserver?.disconnect()
  if (heroImageTimer) window.clearInterval(heroImageTimer)
})



async function adjustPlan() {
  if (!plan.value || !adjustMessage.value.trim()) return

  adjusting.value = true
  adjustError.value = ''
  try {
    const response = await fetch(apiUrl('/api/trip/plan/adjust'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_plan: plan.value,
        user_message: adjustMessage.value.trim()
      })
    })

    if (!response.ok) {
      throw new Error(`请求失败：${response.status}`)
    }

    plan.value = await response.json()
    syncActiveVariant()
    adjustMessage.value = ''

    await nextTick()
    await renderMap()
  } catch (e) {
    adjustError.value = e instanceof Error ? e.message : '调整失败，请稍后重试'
  } finally {
    adjusting.value = false
  }
}

</script>

<template>
  <main class="page" :class="{ 'info-open': infoOpen, 'chat-open': chatOpen }">
    <header class="topbar">
      <div class="brand">
        <span class="brand-icon"><Compass :size="20" /></span>
        <div>
          <span class="eyebrow">AI 旅行创作室 · 实地笔记 第 08 期</span>
          <h1>AI 旅行规划助手</h1>
        </div>
      </div>
      <div class="topbar-actions">
        <div class="topbar-meta">
          <span>{{ destination || '目的地待定' }}</span>
          <i></i>
          <span>{{ days }} 天</span>
          <i></i>
          <span>{{ budget }} 元</span>
        </div>
        <button type="button" class="tool-btn" :class="{ active: infoOpen }" @click="infoOpen = !infoOpen">
          <SlidersHorizontal :size="16" /> 行程资料
        </button>
        <button type="button" class="tool-btn" :class="{ active: chatOpen }" @click="chatOpen = !chatOpen">
          <MessageCircle :size="16" /> AI 对话
        </button>
      </div>
    </header>

    <section class="planner">
      <aside class="info-panel glass-panel">
        <div class="panel-cover">
          <button type="button" class="drawer-close" @click="infoOpen = false" aria-label="关闭行程资料">
            <X :size="16" />
          </button>
          <span class="cover-icon"><MapPin :size="15" /> 行程档案</span>
          <strong>{{ destination || '未设定目的地' }}</strong>
          <small>{{ preferences.length ? preferences.join(' / ') : '等待偏好' }}</small>
        </div>

        <form class="fields" @submit.prevent="submitPlan">
          <label>
            目的地
            <input v-model="destination" type="text" placeholder="例如 成都" />
          </label>

          <div class="row">
            <label>
              天数
              <input v-model.number="days" type="number" min="1" max="14" />
            </label>
            <label>
              预算（元）
              <input v-model.number="budget" type="number" min="100" step="100" />
            </label>
          </div>

          <label>
            出发城市
            <input v-model="departureCity" type="text" placeholder="例如 北京" />
          </label>

          <label>
            出发日期
            <input v-model="travelDate" type="date" />
          </label>

          <div class="row">
            <label>
              酒店预算
              <input v-model.number="hotelBudget" type="number" min="0" step="50" />
            </label>
            <label>
              人数
              <input v-model.number="companions" type="number" min="1" max="20" />
            </label>
          </div>

          <div class="field">
            <span>偏好</span>
            <div class="options">
              <button
                v-for="option in preferenceOptions"
                :key="option"
                type="button"
                :class="{ active: preferences.includes(option) }"
                @click="togglePreference(option)"
              >
                {{ option }}
              </button>
            </div>
          </div>

          <div class="field">
            <span>生成模式</span>
            <div class="segmented">
              <button
                v-for="option in compareOptions"
                :key="option.label"
                type="button"
                :class="{ active: compareMode === option.value }"
                @click="compareMode = option.value"
              >
                {{ option.label }}
              </button>
            </div>
          </div>

          <div class="field">
            <span>交通</span>
            <div class="segmented">
              <button
                v-for="option in transportOptions"
                :key="option.value"
                type="button"
                :class="{ active: transportMode === option.value }"
                @click="changeTransport(option.value)"
              >
                {{ option.label }}
              </button>
            </div>
            <small v-if="routeRecalculating" class="route-note">路线重算中...</small>
            <small v-if="routeError" class="error">{{ routeError }}</small>
          </div>

          <label>
            饮食限制
            <input v-model="dietaryNotes" type="text" placeholder="例如 不吃辣 / 素食" />
          </label>

          <button class="submit" type="submit" :disabled="loading">
            <LoaderCircle v-if="loading" class="spin" :size="17" />
            <Sparkles v-else :size="17" />
            {{ loading ? '生成中...' : (compareMode ? '生成三套对比方案' : '生成行程') }}
          </button>
          <p v-if="loading" class="progress">{{ progress }}</p>
          <div v-if="error" class="form-error">
            <p class="error">{{ error }}</p>
            <button v-if="generationFailed" type="button" class="retry-btn" @click="retryGeneration">
              <RefreshCw :size="15" /> 重试
            </button>
          </div>
        </form>

        <div v-if="historyList.length" class="history">
          <h3>历史行程</h3>
          <div
            v-for="item in historyList"
            :key="item.id"
            class="history-item"
            role="button"
            tabindex="0"
            @click="loadPlanFromHistory(item.id)"
            @keydown.enter="loadPlanFromHistory(item.id)"
          >
            <span class="history-main">
              <History :size="15" />
              <span>{{ item.destination }} {{ item.days }}日游 · {{ item.budget }}元</span>
            </span>
            <span class="history-meta">
              <small>{{ item.created_at }}</small>
              <button
                type="button"
                class="history-delete"
                :disabled="deletingHistoryId === item.id"
                :aria-label="`删除 ${item.destination} 历史行程`"
                @click.stop="deleteHistoryItem(item.id)"
              >
                <LoaderCircle v-if="deletingHistoryId === item.id" class="spin" :size="13" />
                <Trash2 v-else :size="13" />
              </button>
            </span>
          </div>
        </div>

        <div class="memory-card">
          <div class="memory-head">
            <Brain :size="16" />
            <strong>用户记忆</strong>
            <small v-if="memoryMessage">{{ memoryMessage }}</small>
          </div>

          <div class="field">
            <span>偏好</span>
            <div class="options">
              <button
                v-for="option in preferenceOptions"
                :key="'memory-pref-' + option"
                type="button"
                :class="{ active: memoryDraft.preferences.includes(option) }"
                @click="toggleMemoryPreference(option)"
              >
                {{ option }}
              </button>
            </div>
            <div class="memory-add">
              <input v-model="newMemoryPreference" type="text" placeholder="添加自定义偏好" @keyup.enter="addMemoryPreference" />
              <button type="button" class="icon-btn" aria-label="添加偏好" @click="addMemoryPreference">
                <Plus :size="14" />
              </button>
            </div>
            <div v-if="memoryDraft.preferences.length" class="memory-tags">
              <button
                v-for="(item, index) in memoryDraft.preferences"
                :key="'saved-pref-' + item"
                type="button"
                class="memory-tag"
                @click="removeMemoryPreference(index)"
              >
                {{ item }} <X :size="12" />
              </button>
            </div>
          </div>

          <div class="field">
            <span>去过城市</span>
            <div class="memory-add">
              <input v-model="newVisitedCity" type="text" placeholder="添加城市" @keyup.enter="addVisitedCity" />
              <button type="button" class="icon-btn" aria-label="添加城市" @click="addVisitedCity">
                <Plus :size="14" />
              </button>
            </div>
            <div v-if="memoryDraft.visited_cities.length" class="memory-tags">
              <button
                v-for="(city, index) in memoryDraft.visited_cities"
                :key="'city-' + city"
                type="button"
                class="memory-tag"
                @click="removeVisitedCity(index)"
              >
                {{ city }} <X :size="12" />
              </button>
            </div>
          </div>

          <div class="row">
            <label>
              饮食限制
              <input v-model="memoryDraft.dietary_notes" type="text" placeholder="例如 不吃辣" />
            </label>
            <label>
              酒店预算
              <input v-model.number="memoryDraft.hotel_budget" type="number" min="0" step="50" />
            </label>
          </div>

          <div class="field">
            <span>记忆节奏</span>
            <div class="segmented">
              <button
                v-for="option in paceOptions"
                :key="'pace-' + option.value"
                type="button"
                :class="{ active: memoryDraft.pace === option.value }"
                @click="memoryDraft.pace = option.value"
              >
                {{ option.label }}
              </button>
            </div>
          </div>

          <div class="field">
            <span>记忆交通</span>
            <div class="segmented">
              <button
                v-for="option in transportOptions"
                :key="'memory-mode-' + option.value"
                type="button"
                :class="{ active: memoryDraft.transport_mode === option.value }"
                @click="memoryDraft.transport_mode = option.value"
              >
                {{ option.label }}
              </button>
            </div>
          </div>

          <button class="save memory-save" type="button" :disabled="memorySaving" @click="saveMemory">
            <LoaderCircle v-if="memorySaving" class="spin" :size="15" />
            <Save v-else :size="15" />
            {{ memorySaving ? '保存中...' : '保存记忆' }}
          </button>
        </div>
      </aside>

      <section class="canvas">
        <section class="hero">
          <Transition name="hero-fade">
            <div
              :key="heroImageIndex"
              class="hero-bg"
              :style="{ '--hero-image': `url(${heroImages[heroImageIndex]})` }"
              role="img"
              :aria-label="heroTitle + ' 的旅行杂志封面'"
            ></div>
          </Transition>
          <div class="hero-overlay">
            <span class="eyebrow">杂志式行程</span>
            <h2>{{ heroTitle }}</h2>
            <p>{{ heroSubtitle }}</p>
            <div class="hero-stats">
              <div v-for="item in planStats" :key="item.label">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
            <div v-if="!plan" class="hero-actions">
              <button type="button" class="hero-cta" @click="infoOpen = true">
                <Sparkles :size="17" /> 开始规划
              </button>
              <button type="button" class="hero-cta ghost" @click="chatOpen = true">
                <MessageCircle :size="17" /> AI 对话
              </button>
            </div>
          </div>
          <div v-if="heroImages.length > 1" class="hero-slides" aria-label="切换画布图片">
            <button
              v-for="(image, index) in heroImages"
              :key="image"
              type="button"
              :class="{ active: heroImageIndex === index }"
              :aria-label="`切换画布图片 ${index + 1}`"
              @click="setHeroImage(index)"
            ></button>
          </div>
        </section>

        <section v-if="loading" class="loading-board glass-panel">
          <div class="loading-line">
            <span>{{ progress || '准备规划中' }}</span>
            <strong>{{ progressPercent }}%</strong>
          </div>
          <div class="progress-track">
            <span :style="{ width: `${progressPercent}%` }"></span>
          </div>
          <div class="progress-steps">
            <span
              v-for="step in progressSteps"
              :key="step"
              :class="{ active: step === progressStep }"
            >
              {{ step }}
            </span>
          </div>
        </section>

                <section v-if="plan" class="result">
          <header class="result-head reveal in-view">
            <div class="masthead">
              <span class="eyebrow">生成行程 · 旅行杂志</span>
              <h2>{{ plan.destination }} {{ plan.days }} 日游</h2>
            </div>
            <div class="head-actions">
              <span v-if="plan.quality_report" class="quality-chip" :class="{ ok: plan.quality_report.passed, warn: !plan.quality_report.passed }">
                {{ plan.quality_report.passed ? '质量校验通过' : `有待完善 ${plan.quality_report.issues.length} 项` }}
              </span>
              <span class="cost">预算 {{ plan.budget }} 元</span>
              <button type="button" class="save" @click="saveCurrentPlan">
                <Save :size="16" /> 保存行程
              </button>
              <button type="button" class="export-btn" @click="exportMarkdown">
                <Download :size="15" /> 文本
              </button>
              <button type="button" class="export-btn" @click="exportPdf">
                <FileText :size="15" /> 打印
              </button>
              <button type="button" class="export-btn" @click="exportShareImage">
                <Share2 :size="15" /> 分享图
              </button>
            </div>
          </header>

          <div v-if="planVariants.length > 1" class="variant-bar reveal in-view" aria-label="方案对比">
            <button
              v-for="(variant, index) in planVariants"
              :key="variant.variant_theme || variant.variant_label || index"
              type="button"
              class="variant-option"
              :class="{ active: activeVariantIndex === index }"
              @click="selectVariant(index)"
            >
              <span class="variant-name">{{ variant.variant_label || variantFallbackLabel(index) }}</span>
              <strong>{{ variant.total_cost || variant.budget }} 元</strong>
              <small>{{ variantSpotCount(variant) }} 个景点 · {{ variantPaceHint(variant) }}</small>
            </button>
          </div>

          <p v-if="plan.overview" class="overview reveal">{{ plan.overview }}</p>

          <div class="quick-grid reveal">
            <div v-if="plan.weather" class="mini-card weather">
              <span>天气</span>
              <strong>{{ plan.weather.city }} · {{ plan.weather.weather }} · {{ plan.weather.temperature }}℃</strong>
              <small>风向 {{ plan.weather.wind_direction }} · 风力 {{ plan.weather.wind_power }} · 湿度 {{ plan.weather.humidity }}%</small>
            </div>
            <div v-if="plan.hotels && plan.hotels.length" class="mini-card">
              <span>首选酒店</span>
              <strong>{{ plan.hotels[0].name }}</strong>
              <small>{{ plan.hotels[0].category }} · {{ plan.hotels[0].address }}</small>
            </div>
            <div v-if="plan.budget_report" class="mini-card">
              <span>预算状态</span>
              <strong>{{ plan.budget_report.within_budget ? '预算内' : '超出预算' }}</strong>
              <small>总花费 {{ plan.budget_report.total_cost }} 元 · 结余 {{ plan.budget_report.savings }} 元</small>
            </div>
          </div>

          <div class="atlas-grid reveal">
            <div class="map-stage">
              <div class="map-tools">
                <div class="day-tabs">
                  <button
                    v-for="day in plan.daily_plans"
                    :key="day.day"
                    type="button"
                    :class="{ active: selectedDay === day.day }"
                    @click="selectDay(day.day)"
                  >
                    第 {{ day.day }} 天
                  </button>
                </div>
                <div class="play-controls">
                  <div class="speed-seg" aria-label="播放速度">
                    <button
                      v-for="speed in [1, 2, 4]"
                      :key="speed"
                      type="button"
                      :class="{ active: playSpeed === speed }"
                      @click="setPlaySpeed(speed)"
                    >
                      {{ speed }} 倍
                    </button>
                  </div>
                  <button v-if="playing" type="button" class="stop-btn" @click="stopRoutes">
                    <X :size="16" /> 停止
                  </button>
                </div>
                <button type="button" class="play-btn" :disabled="playing" @click="playRoutes">
                  <LoaderCircle v-if="playing" class="spin" :size="16" />
                  <Play v-else :size="16" />
                  {{ playing ? '播放中...' : '播放路线' }}
                </button>
              </div>
              <div v-if="activeRouteModes.length" class="route-legend">
                <span v-for="mode in activeRouteModes" :key="mode">
                  <i :style="{ background: routeModeColors[mode] }"></i>
                  {{ routeModeLabels[mode] }}
                </span>
              </div>
              <p v-if="routeProgress" class="route-progress">{{ routeProgress }}</p>
              <div ref="mapEl" class="map"></div>
            </div>

            <aside class="dossier">
              <div v-if="activeDay" class="featured-day">
                <span class="eyebrow">当前日程</span>
                <h3>第 {{ activeDay.day }} 天 · {{ activeDay.theme }}</h3>
                <div class="featured-points">
                  <button
                    v-for="spot in activeDay.spots"
                    :key="spot.name"
                    type="button"
                    class="featured-spot"
                    :class="{ active: activeSpotName === spot.name && activeSpotDay === activeDay.day }"
                    @click="focusSpot(spot.name, activeDay.day)"
                  >
                    {{ spot.name }}
                  </button>
                </div>
              </div>
              <div class="adjust">
                <input v-model="adjustMessage" placeholder="调整指令" />
                <button type="button" :disabled="adjusting" @click="adjustPlan">
                  <LoaderCircle v-if="adjusting" class="spin" :size="16" />
                  <RefreshCw v-else :size="16" />
                  {{ adjusting ? '调整中...' : '调整行程' }}
                </button>
              </div>
              <p v-if="adjustError" class="error">{{ adjustError }}</p>
            </aside>
          </div>

          <div class="chapter-head reveal">
            <span class="eyebrow">行程章节</span>
            <h3>每日行程</h3>
          </div>

          <div class="chapters">
            <article v-for="day in plan.daily_plans" :key="day.day" class="day reveal">
              <span class="chapter-no">{{ String(day.day).padStart(2, '0') }}</span>
              <div class="chapter-body">
                <h3>第 {{ day.day }} 天 · {{ day.theme }}</h3>
                <div v-if="forecastForDay(day)" class="day-weather">
                  <div class="day-weather-head">
                    <span>{{ forecastForDay(day)!.date }} · {{ forecastForDay(day)!.week }}</span>
                    <strong>{{ forecastForDay(day)!.day_weather }} / {{ forecastForDay(day)!.night_weather }}</strong>
                  </div>
                  <div class="day-weather-meta">
                    <span>{{ forecastForDay(day)!.temp_min }}~{{ forecastForDay(day)!.temp_max }}℃</span>
                    <span>降水 {{ forecastForDay(day)!.precipitation_probability }}%</span>
                    <span>{{ forecastForDay(day)!.wind_direction }} {{ forecastForDay(day)!.wind_power }}</span>
                  </div>
                  <small v-if="forecastForDay(day)!.suggestion">{{ forecastForDay(day)!.suggestion }}</small>
                </div>
                <div class="spots">
                  <div
                    v-for="(spot, spotIndex) in day.spots"
                    :key="spot.name"
                    class="spot"
                    :class="{ active: activeSpotName === spot.name && activeSpotDay === day.day }"
                    role="button"
                    tabindex="0"
                    @click="focusSpot(spot.name, day.day)"
                    @keyup.enter="focusSpot(spot.name, day.day)"
                  >
                    <span class="index">{{ String(spotIndex + 1).padStart(2, '0') }}</span>
                    <strong>{{ spot.name }}</strong>
                    <span>{{ spot.duration }}</span>
                    <p>{{ spot.description }}</p>
                    <small>{{ spot.address }}</small>
                    <small v-if="routeForSpot(spot.name, day.day)" class="route">
                      {{ formatRoute(spot.name, day.day) }}
                    </small>
                    <a
                      v-if="spot.booking_url"
                      :href="spot.booking_url"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="spot-booking"
                      @click.stop
                    >
                      <ExternalLink :size="13" />
                      {{ spot.booking_label || '购票 / 预约' }}
                    </a>
                  </div>
                </div>
                <div v-if="day.foods && day.foods.length" class="foods">
                  <div
                    v-for="(food, foodIndex) in day.foods"
                    :key="food.name"
                    class="food"
                    :class="{ active: activeSpotName === food.name && activeSpotDay === day.day }"
                    role="button"
                    tabindex="0"
                    @click="focusSpot(food.name, day.day)"
                    @keyup.enter="focusSpot(food.name, day.day)"
                  >
                    <span class="index">{{ String(foodIndex + 1).padStart(2, '0') }}</span>
                    <strong>{{ food.name }}</strong>
                    <span>{{ food.cuisine }} · {{ food.price_range }}</span>
                    <p>{{ food.description }}</p>
                    <small>{{ food.address }} · {{ food.best_time }}</small>
                  </div>
                </div>
              </div>
            </article>
          </div>

          <div class="backmatter reveal">
            <section v-if="plan.budget_report" class="budget">
              <h3>预算报告</h3>
              <p :class="plan.budget_report.within_budget ? 'ok' : 'over'">
                {{ plan.budget_report.within_budget ? '预算内' : '超出预算' }} · 总花费 {{ plan.budget_report.total_cost }} 元
              </p>
              <ul v-if="plan.budget_report.suggestions && plan.budget_report.suggestions.length">
                <li v-for="suggestion in plan.budget_report.suggestions" :key="suggestion">{{ suggestion }}</li>
              </ul>
              <div v-if="budgetDetail" class="budget-detail">
                <div class="budget-summary">
                  <div class="budget-summary-block">
                    <span>预计总花费</span>
                    <strong>{{ totalBudgetRangeText() }}</strong>
                    <small>AI 弹性区间</small>
                  </div>
                  <div class="budget-summary-block actual" :class="budgetComparison.tone">
                    <span>实际总花费</span>
                    <strong>{{ actualTotal }} 元</strong>
                    <small>{{ budgetComparison.label }}</small>
                  </div>
                  <div class="budget-summary-block">
                    <span>总预算</span>
                    <strong>{{ budgetDetail.budget }} 元</strong>
                    <small>计划上限</small>
                  </div>
                </div>

                <div class="budget-compare" :class="budgetComparison.tone">
                  <div class="budget-compare-track">
                    <span
                      class="budget-compare-range"
                      :style="{
                        left: `${budgetScale.minPct}%`,
                        width: `${Math.max(budgetScale.maxPct - budgetScale.minPct, 2)}%`
                      }"
                    ></span>
                    <span
                      v-if="budgetComparison.actual > 0"
                      class="budget-compare-dot"
                      :style="{ left: `${budgetScale.actualPct}%` }"
                    ></span>
                  </div>
                  <div class="budget-compare-labels">
                    <span>0</span>
                    <span>预计区间 {{ totalBudgetRangeText() }}</span>
                    <span>{{ budgetScale.budget }} 预算</span>
                  </div>
                </div>

                <div class="budget-toolbar">
                  <span class="budget-toolbar-title">每日记账</span>
                  <button
                    type="button"
                    class="budget-save-btn"
                    :disabled="savingExpenses"
                    @click="saveExpenses"
                  >
                    <Save :size="15" />
                    {{ savingExpenses ? '保存中...' : '保存记账' }}
                  </button>
                </div>
                <p v-if="expenseSaveMessage" class="budget-save-note">{{ expenseSaveMessage }}</p>

                <div class="ledger-nav">
                  <button
                    v-for="day in budgetDetail.days"
                    :key="day.day"
                    type="button"
                    class="ledger-day-tab"
                    :class="{ active: activeLedgerDay === day.day }"
                    @click="setLedgerDay(day.day)"
                  >
                    第 {{ day.day }} 天
                  </button>
                </div>
                <div class="budget-ledger">
                  <div
                    v-for="day in budgetDetail.days"
                    :key="day.day"
                    class="budget-day ledger-card"
                    :class="{ active: activeLedgerDay === day.day }"
                    :style="ledgerStackStyle(day.day)"
                  >
                    <div class="budget-day-head">
                      <span>第 {{ day.day }} 天</span>
                      <strong>{{ budgetRangeText(day.min_amount, day.max_amount, day.typical, day.amount) }}</strong>
                    </div>
                    <TransitionGroup name="expense-slide" tag="div" class="expense-list">
                      <div
                        v-for="expense in actualExpensesForDay(day.day)"
                        :key="expense.rowKey"
                        class="expense-row"
                        :class="{ custom: isCustomCategory(expense.category) }"
                      >
                        <template v-if="isCustomCategory(expense.category)">
                          <input
                            v-model="expense.category"
                            type="text"
                            placeholder="花费项目"
                            class="expense-category-input"
                            :aria-label="`第 ${day.day} 天 自定义花费项目`"
                          />
                          <button
                            type="button"
                            class="expense-remove"
                            :aria-label="`删除 第 ${day.day} 天 ${expense.category || '自定义'} 花费`"
                            @click="removeExpense(expense.rowKey!)"
                          >
                            <X :size="13" />
                          </button>
                        </template>
                        <template v-else>
                          <span class="expense-category">{{ expense.category }}</span>
                          <small class="expense-range">{{ categoryRangeText(expense.category) }}</small>
                        </template>
                        <input
                          v-model.number="expense.amount"
                          type="number"
                          min="0"
                          step="1"
                          placeholder="未记录"
                          :aria-label="`第 ${day.day} 天 ${expense.category || '自定义'} 实际花费`"
                        />
                        <input
                          v-model="expense.note"
                          type="text"
                          placeholder="备注"
                          :aria-label="`第 ${day.day} 天 ${expense.category || '自定义'} 备注`"
                        />
                      </div>
                    </TransitionGroup>
                    <div class="expense-quick-add">
                      <span>添加花费</span>
                      <div class="expense-quick-add-buttons">
                        <button
                          v-for="name in customExpenseOptions"
                          :key="name"
                          type="button"
                          @click="addExpense(day.day, name)"
                        >
                          + {{ name }}
                        </button>
                        <button type="button" class="custom" @click="addExpense(day.day)">
                          + 自定义
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="budget-categories">
                  <div
                    v-for="category in budgetDetail.categories"
                    :key="category.category"
                    class="budget-category"
                  >
                    <div class="budget-category-head">
                      <span>{{ category.category }}</span>
                      <strong>{{ budgetRangeText(category.min_amount, category.max_amount, category.typical, category.amount) }}</strong>
                      <i>{{ budgetCategoryPercent(category.typical || category.amount) }}%</i>
                    </div>
                    <div class="budget-track">
                      <span :style="{ width: `${budgetCategoryPercent(category.typical || category.amount)}%` }"></span>
                    </div>
                    <small v-if="category.note" class="budget-note">{{ category.note }}</small>
                  </div>
                </div>
              </div>
            </section>

            <section v-if="plan.hotels && plan.hotels.length" class="hotel">
              <h3>推荐酒店</h3>
              <div v-for="(hotel, hotelIndex) in plan.hotels.slice(0, 3)" :key="hotel.name" class="hotel-item">
                <span class="index">{{ String(hotelIndex + 1).padStart(2, '0') }}</span>
                <strong>{{ hotel.name }}</strong>
                <span>{{ hotel.category }} {{ hotel.price_hint }}</span>
                <p>{{ hotel.address }}</p>
                <small v-if="hotel.phone">电话：{{ hotel.phone }}</small>
              </div>
            </section>

            <section v-if="plan.nearby && plan.nearby.length" class="nearby">
              <h3>酒店周边</h3>
              <ul>
                <li v-for="poi in plan.nearby" :key="poi.name">
                  {{ poi.name }} · {{ poi.distance }}米 · {{ poi.category }}
                </li>
              </ul>
            </section>

            <footer v-if="plan.notes.length" class="notes">
              <h3>注意事项</h3>
              <ul>
                <li v-for="note in plan.notes" :key="note">{{ note }}</li>
              </ul>
            </footer>
          </div>
            <div ref="shareCardEl" class="share-card">
              <span>AI 旅行杂志</span>
              <h2>{{ plan.destination }} {{ plan.days }} 日游</h2>
              <p>{{ plan.overview }}</p>
              <div v-for="day in plan.daily_plans.slice(0, 3)" :key="day.day">
                <strong>第 {{ day.day }} 天 · {{ day.theme }}</strong>
                <span>{{ day.spots.map((s) => s.name).join(' / ') }}</span>
              </div>
              <small>总预算 {{ plan.budget }} 元 · {{ plan.hotels?.[0]?.name || '' }}</small>
            </div>
          </section>

          <section v-else class="empty">
          <div class="empty-inner">
            <span class="eyebrow">开始规划</span>
            <h2>把目的地放进画布</h2>
            <p>目的地、预算、偏好和 AI 对话，都会汇成一本随时可以出发的旅行杂志。</p>
          </div>
        </section>
      </section>

      <aside class="chat-panel glass-panel">
        <div class="chat-head">
          <div class="chat-head-top">
            <div>
              <span class="eyebrow"><MessageCircle :size="15" /> 旅行管家</span>
              <h2>AI 对话</h2>
            </div>
            <div class="chat-head-actions">
              <button type="button" class="chat-new-btn" :disabled="chatSending" @click="startNewChat">
                <Plus :size="15" /> 新对话
              </button>
              <button type="button" class="drawer-close chat-close" @click="chatOpen = false" aria-label="关闭AI对话">
                <X :size="16" />
              </button>
            </div>
          </div>
          <p>描述目的地、预算和偏好，AI 会补全信息并自动生成规划。</p>
          <div class="chat-session-bar">
            <button
              type="button"
              class="chat-history-toggle"
              :class="{ open: chatHistoryOpen }"
              @click="chatHistoryOpen = !chatHistoryOpen"
            >
              <History :size="15" />
              <span>{{ activeChatTitle }}</span>
              <small v-if="activeChatMessageCount">{{ activeChatMessageCount }} 条</small>
            </button>
          </div>
          <div v-if="chatHistoryOpen" class="chat-history-list">
            <p v-if="chatHistoryError" class="chat-history-error">{{ chatHistoryError }}</p>
            <div
              v-for="session in chatSessions"
              :key="session.id"
              class="chat-session-item"
              :class="{ active: session.id === activeChatSessionId }"
              role="button"
              tabindex="0"
              @click="loadChatSession(session.id)"
              @keydown.enter="loadChatSession(session.id)"
            >
              <span class="chat-session-title">{{ session.title }}</span>
              <small>{{ session.message_count }} 条 · {{ session.updated_at }}</small>
              <button
                type="button"
                class="chat-session-delete"
                :aria-label="`删除会话 ${session.title}`"
                @click.stop="deleteChatSession(session.id)"
              >
                <Trash2 :size="13" />
              </button>
            </div>
            <p v-if="!chatSessions.length && !chatHistoryError" class="chat-history-empty">还没有历史对话</p>
          </div>
        </div>
        <div ref="chatScrollEl" class="chat-messages" aria-live="polite">
          <div
            v-for="(msg, index) in messages"
            :key="index"
            :class="['chat-msg', msg.role]"
          >
            {{ msg.content }}
          </div>
          <div v-if="chatSending" class="chat-msg assistant typing" aria-label="AI 正在输入">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
        <div class="chat-input">
          <input
            v-model="chatInput"
            placeholder="例如：我想从北京去成都玩 3 天，预算 3000"
            @keyup.enter="sendMessage"
          />
          <button type="button" :disabled="chatSending" @click="sendMessage" aria-label="发送消息">
            <LoaderCircle v-if="chatSending" class="spin" :size="16" />
            <Send v-else :size="16" />
            {{ chatSending ? '发送中' : '发送' }}
          </button>
        </div>
      </aside>
    </section>

    <div v-if="infoOpen || chatOpen" class="drawer-backdrop" @click="infoOpen = false; chatOpen = false"></div>
  </main>
</template>

<style>
* {
  box-sizing: border-box;
}

.page {
  min-height: 100vh;
  position: relative;
  overflow-x: hidden;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 18px;
  padding: 22px 28px 10px;
  color: #fffaf0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-icon {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(255, 250, 240, 0.32);
  border-radius: 50%;
  background: rgba(255, 250, 240, 0.12);
  color: #f2c98a;
  flex: none;
}

.topbar h1 {
  margin: 2px 0 0;
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 700;
  line-height: 1.1;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #e9a46f;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

.topbar-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  color: rgba(255, 250, 240, 0.84);
  font-size: 13px;
  font-weight: 700;
}

.topbar-meta i {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: rgba(255, 250, 240, 0.55);
}

.planner {
  display: grid;
  grid-template-columns: minmax(250px, 310px) minmax(440px, 1fr) minmax(280px, 360px);
  gap: 20px;
  max-width: 1560px;
  margin: 0 auto;
  padding: 16px 26px 30px;
  align-items: start;
}

.glass-panel {
  background: rgba(255, 250, 240, 0.86);
  border: 1px solid rgba(255, 250, 240, 0.72);
  box-shadow: 0 24px 60px rgba(16, 35, 31, 0.18);
  backdrop-filter: blur(18px);
}

.info-panel,
.chat-panel {
  border-radius: 8px;
  padding: 16px;
  display: grid;
  gap: 14px;
}

.info-panel,
.chat-panel {
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 32px);
  overflow-y: auto;
}

.panel-cover {
  min-height: 190px;
  border-radius: 8px;
  padding: 18px;
  display: grid;
  align-content: end;
  gap: 5px;
  color: #fffaf0;
  background:
    linear-gradient(180deg, rgba(16, 32, 36, 0.02), rgba(16, 32, 36, 0.84)),
    url("https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=900&q=80") center / cover;
  overflow: hidden;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}

.cover-icon {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.panel-cover span,
.panel-cover small {
  color: rgba(255, 250, 240, 0.84);
  font-size: 12px;
  font-weight: 700;
}

.panel-cover strong {
  font-family: var(--font-display);
  font-size: 34px;
  line-height: 1.02;
}

.fields {
  display: grid;
  gap: 12px;
}

label {
  display: grid;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #2e3d38;
}

input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid rgba(29, 42, 38, 0.16);
  border-radius: 6px;
  font-size: 14px;
  background: rgba(255, 255, 255, 0.76);
  color: #1d2a26;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

input:focus {
  border-color: #c56a47;
  box-shadow: 0 0 0 3px rgba(197, 106, 71, 0.18);
  background: #ffffff;
}

.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.field {
  display: grid;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #2e3d38;
}

.options,
.segmented {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.options button,
.segmented button {
  min-height: 44px;
  padding: 8px 12px;
  border: 1px solid rgba(29, 42, 38, 0.16);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  color: #2e3d38;
  cursor: pointer;
  font-size: 13px;
  transition: transform 0.18s ease, background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}

.options button:hover,
.segmented button:hover {
  transform: translateY(-1px);
  border-color: rgba(197, 106, 71, 0.4);
}

.options button.active,
.segmented button.active {
  background: #c56a47;
  border-color: #c56a47;
  color: #ffffff;
}

.submit {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 46px;
  padding: 12px;
  border: 0;
  border-radius: 6px;
  background: linear-gradient(135deg, #c56a47, #a84d38);
  color: #ffffff;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 12px 26px rgba(168, 77, 56, 0.24);
  transition: transform 0.2s ease, box-shadow 0.2s ease, filter 0.2s ease;
}

.submit:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 16px 32px rgba(168, 77, 56, 0.28);
}

.submit:disabled {
  opacity: 0.62;
  cursor: not-allowed;
}

.error {
  color: #b3261e;
  margin: 0;
}

.form-error {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.form-error .error {
  margin: 0;
}

.retry-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid rgba(197, 106, 71, 0.45);
  border-radius: 8px;
  background: rgba(197, 106, 71, 0.12);
  color: #b8543a;
  font-weight: 600;
  cursor: pointer;
}

.retry-btn:hover {
  background: rgba(197, 106, 71, 0.2);
}

.progress {
  margin: 0;
  color: #1c4b40;
  font-weight: 600;
}

.canvas {
  display: grid;
  gap: 18px;
  min-width: 0;
}

.hero {
  position: relative;
  min-height: 470px;
  border-radius: 8px;
  overflow: clip;
  box-shadow: 0 30px 80px rgba(16, 35, 31, 0.3);
  isolation: isolate;
}

.hero-bg {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(13, 25, 22, 0.86), rgba(13, 25, 22, 0.18) 60%, rgba(13, 25, 22, 0.52)),
    url("https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?auto=format&fit=crop&w=1800&q=85") center / cover;
  transform: scale(1.06) translate3d(-8px, var(--parallax-y, 0px), 0);
  animation: heroDrift 20s ease-in-out infinite alternate;
  will-change: transform;
  z-index: -1;
}

.hero-overlay {
  min-height: 470px;
  display: grid;
  align-content: end;
  gap: 14px;
  padding: 42px;
  color: #fffaf0;
}

.hero-overlay .eyebrow,
.hero-overlay h2,
.hero-overlay p,
.hero-stats {
  animation: riseIn 0.6s ease both;
}

.hero-overlay h2 {
  margin: 0;
  max-width: 680px;
  font-family: var(--font-display);
  font-size: 58px;
  line-height: 1.02;
  animation-delay: 0.05s;
}

.hero-overlay p {
  max-width: 720px;
  margin: 0;
  color: rgba(255, 250, 240, 0.88);
  line-height: 1.8;
  animation-delay: 0.12s;
}

.hero-stats {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 6px;
  animation-delay: 0.2s;
}

.hero-stats div {
  min-width: 112px;
  padding: 10px 12px;
  border: 1px solid rgba(255, 250, 240, 0.28);
  border-radius: 6px;
  background: rgba(255, 250, 240, 0.14);
  backdrop-filter: blur(8px);
}

.hero-stats span {
  display: block;
  color: rgba(255, 250, 240, 0.7);
  font-size: 12px;
}

.hero-stats strong {
  display: block;
  margin-top: 3px;
  font-size: 18px;
}

.result {
  background: rgba(255, 253, 245, 0.96);
  border: 1px solid rgba(255, 250, 240, 0.8);
  border-radius: 8px;
  padding: 28px;
  box-shadow: 0 24px 60px rgba(16, 35, 31, 0.16);
  animation: riseIn 0.5s ease both;
}

.result-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.result-head h2 {
  margin: 4px 0 0;
  font-family: var(--font-display);
  font-size: 30px;
}

.cost {
  color: #a84d38;
  font-weight: 700;
}

.overview {
  max-width: 780px;
  color: #4d5c55;
  line-height: 1.8;
  margin: 0 0 4px;
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin: 18px 0;
}

.mini-card {
  position: relative;
  display: grid;
  gap: 6px;
  min-height: 118px;
  padding: 16px 16px 14px;
  border: 1px solid rgba(29, 42, 38, 0.12);
  border-radius: 8px;
  background: #fffdf5;
  overflow: hidden;
}

.mini-card::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: linear-gradient(#c56a47, #2f6f5d);
}

.mini-card span {
  color: #a84d38;
  font-size: 12px;
  font-weight: 800;
}

.mini-card strong {
  line-height: 1.35;
}

.mini-card small {
  color: #5c6a63;
  line-height: 1.5;
}

.map-stage {
  border: 1px solid rgba(29, 42, 38, 0.12);
  border-radius: 8px;
  background: #efe6d5;
  padding: 14px;
  margin: 18px 0;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
}

.map-tools {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 12px 0;
  flex-wrap: wrap;
}

.day-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.day-tabs button {
  min-height: 44px;
  padding: 8px 14px;
  border: 1px solid rgba(29, 42, 38, 0.16);
  border-radius: 6px;
  background: #fffdf5;
  color: #334155;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.day-tabs button:hover {
  transform: translateY(-1px);
}

.day-tabs button.active {
  background: #1c4b40;
  border-color: #1c4b40;
  color: #ffffff;
}

.play-btn,
.adjust button,
.chat-input button,
.save {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 0;
  border-radius: 6px;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.play-btn {
  min-height: 44px;
  padding: 9px 15px;
  background: #1c4b40;
  color: #fffaf0;
  font-size: 13px;
}

.play-btn:hover:not(:disabled),
.save:hover {
  background: #2f6f5d;
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(28, 75, 64, 0.25);
}

.play-btn:disabled,
.adjust button:disabled,
.chat-input button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.route-progress {
  margin: 0 0 10px;
  color: #1c4b40;
  font-size: 13px;
  font-weight: 600;
}

.route-legend {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin: 10px 0 0;
}

.route-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #5c6a63;
  font-size: 12px;
  font-weight: 700;
}

.route-legend i {
  width: 18px;
  height: 4px;
  border-radius: 999px;
}

.route-note {
  color: #a84d38;
  font-size: 12px;
  font-weight: 600;
}

.map {
  width: 100%;
  height: 470px;
  border: 1px solid rgba(29, 42, 38, 0.14);
  border-radius: 8px;
  margin: 12px 0 0;
  overflow: hidden;
  background: #dfe9e2;
}

.featured-day {
  padding: 16px 0 4px;
}

.featured-day h3 {
  margin: 4px 0 10px;
  font-family: var(--font-display);
  font-size: 24px;
}

.featured-points {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.featured-points span {
  padding: 7px 10px;
  border-radius: 999px;
  background: #e7f2eb;
  color: #1c4b40;
  font-size: 13px;
  font-weight: 700;
}

.adjust {
  display: flex;
  gap: 8px;
  margin: 14px 0;
}

.adjust input {
  flex: 1;
  min-height: 42px;
}

.adjust button {
  min-height: 44px;
  padding: 10px 16px;
  background: #c56a47;
  color: #ffffff;
  font-size: 14px;
  white-space: nowrap;
}

.adjust button:hover:not(:disabled),
.chat-input button:hover:not(:disabled) {
  background: #b35c43;
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(179, 92, 67, 0.25);
}

.day {
  border-top: 1px solid rgba(29, 42, 38, 0.12);
  padding: 24px 0;
  animation: riseIn 0.42s ease both;
}

.day h3 {
  margin: 0 0 14px;
  font-family: var(--font-display);
  font-size: 20px;
}

.day-weather {
  display: grid;
  gap: 6px;
  margin: 12px 0;
  padding: 10px 12px;
  border-left: 3px solid #d99a3d;
  border-radius: 4px;
  background: linear-gradient(135deg, rgba(255, 253, 245, 0.96), rgba(241, 247, 242, 0.92));
  color: #2e3d38;
}

.day-weather-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.day-weather-head span {
  color: #7c8a82;
  font-size: 11px;
  font-weight: 700;
}

.day-weather-head strong {
  color: #1c4b40;
  font-size: 15px;
}

.day-weather-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  color: #4d5c55;
  font-size: 12px;
  font-weight: 700;
}

.day-weather small {
  color: #a84d38;
  font-size: 12px;
  line-height: 1.45;
}

@media (max-width: 640px) {
  .day-weather-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }
}
.spots {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.spot,
.food,
.hotel-item {
  position: relative;
  border: 1px solid rgba(29, 42, 38, 0.12);
  border-radius: 8px;
  padding: 34px 14px 14px;
  display: grid;
  gap: 6px;
  background: #fffdf5;
  transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease;
}

.spot:hover,
.food:hover,
.hotel-item:hover {
  transform: translateY(-3px);
  box-shadow: 0 16px 32px rgba(24, 38, 40, 0.12);
  border-color: rgba(197, 106, 71, 0.28);
}

.index {
  position: absolute;
  top: 12px;
  right: 14px;
  font-family: var(--font-display);
  color: #c56a47;
  font-size: 13px;
  font-weight: 700;
}

.spot span,
.food span {
  color: #1c4b40;
  font-size: 13px;
  font-weight: 600;
}

.spot p,
.food p {
  margin: 0;
  color: #4d5c55;
  font-size: 14px;
  line-height: 1.6;
}

.spot small,
.food small {
  color: #7c8a82;
}

.foods {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.food {
  background: #fff8ea;
}

.budget {
  border-top: 1px solid rgba(29, 42, 38, 0.12);
  padding-top: 16px;
}

.budget h3,
.hotel h3,
.nearby h3,
.notes h3 {
  margin: 0 0 10px;
  font-family: var(--font-display);
  font-size: 18px;
}

.budget p {
  font-weight: 700;
  margin: 0 0 10px;
}

.budget .ok {
  color: #1c4b40;
}

.budget .over {
  color: #b3261e;
}

.budget ul,
.nearby ul,
.notes ul {
  margin: 0;
  padding-left: 20px;
  color: #4d5c55;
  line-height: 1.8;
}

.hotel,
.nearby {
  border-top: 1px solid rgba(29, 42, 38, 0.12);
  margin-top: 12px;
  padding-top: 12px;
}

.hotel-item {
  margin-bottom: 8px;
}

.hotel-item span {
  color: #a84d38;
  font-size: 13px;
  font-weight: 600;
}

.hotel-item p {
  margin: 0;
  color: #4d5c55;
  font-size: 14px;
}

.hotel-item small {
  color: #7c8a82;
}

.notes {
  border-top: 1px solid rgba(29, 42, 38, 0.12);
  padding-top: 16px;
}

.route {
  color: #a84d38;
}

.spot-booking {
  display: inline-flex;
  align-items: center;
  justify-self: start;
  gap: 5px;
  margin-top: 4px;
  padding: 6px 11px;
  border: 1px solid rgba(197, 106, 71, 0.3);
  border-radius: 999px;
  background: #fff3e8;
  color: #a84d38;
  font-size: 12px;
  font-weight: 800;
  text-decoration: none;
  transition: background 0.16s ease, color 0.16s ease, transform 0.16s ease;
}

.spot-booking:hover {
  background: #c56a47;
  color: #ffffff;
  transform: translateY(-1px);
}

.empty {
  position: relative;
  background:
    linear-gradient(rgba(255, 253, 245, 0.82), rgba(255, 253, 245, 0.94)),
    url("https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1400&q=70") center / cover;
  border: 1px solid rgba(255, 250, 240, 0.8);
  border-radius: 8px;
  min-height: 380px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #2e3d38;
  overflow: hidden;
  box-shadow: 0 20px 50px rgba(16, 35, 31, 0.16);
  animation: riseIn 0.5s ease both;
}

.empty::before {
  content: "";
  position: absolute;
  inset: 18px;
  border: 1px solid rgba(197, 106, 71, 0.32);
  border-radius: 8px;
  pointer-events: none;
}

.empty-inner {
  position: relative;
  max-width: 520px;
  padding: 34px;
  text-align: center;
}

.empty h2 {
  margin: 8px 0;
  font-family: var(--font-display);
  font-size: 38px;
}

.empty p {
  margin: 0;
  color: #5c6a63;
  line-height: 1.8;
}

.loading-board {
  border-radius: 8px;
  padding: 18px;
  display: grid;
  gap: 12px;
  animation: riseIn 0.4s ease both;
}

.loading-line {
  display: flex;
  justify-content: space-between;
  color: #2e3d38;
  font-weight: 800;
}

.progress-track {
  height: 8px;
  border-radius: 999px;
  background: rgba(29, 42, 38, 0.12);
  overflow: hidden;
}

.progress-track span {
  position: relative;
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #c56a47, #1c4b40);
  transition: width 0.3s ease;
  overflow: hidden;
}

.progress-track span::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.45), transparent);
  animation: shimmer 1.6s linear infinite;
}

.progress-steps {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.progress-steps span {
  padding: 6px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.64);
  color: #5c6a63;
  font-size: 12px;
  font-weight: 700;
}

.progress-steps span.active {
  background: #1c4b40;
  color: #fffaf0;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.quality-chip {
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.quality-chip.ok {
  background: rgba(28, 75, 64, 0.1);
  color: #1c4b40;
}

.quality-chip.warn {
  background: rgba(197, 106, 71, 0.12);
  color: #a84d38;
}

.save {
  min-height: 44px;
  padding: 8px 14px;
  background: #1c4b40;
  color: #ffffff;
  font-size: 13px;
}

.history {
  border-top: 1px solid rgba(29, 42, 38, 0.12);
  margin-top: 8px;
  padding-top: 14px;
}

.history h3 {
  margin: 0 0 10px;
  font-family: var(--font-display);
  font-size: 17px;
}

.history-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  margin-bottom: 8px;
  padding: 10px 12px;
  border: 1px solid rgba(29, 42, 38, 0.12);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.66);
  color: #1f2933;
  text-align: left;
  cursor: pointer;
  font-size: 14px;
  transition: border-color 0.2s ease, transform 0.2s ease, background 0.2s ease;
}

.history-item:hover {
  border-color: rgba(197, 106, 71, 0.35);
  transform: translateY(-1px);
  background: #ffffff;
}

.history-main {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #24453c;
}

.history-main svg {
  color: #c56a47;
  flex: none;
}

.history-item small {
  color: #7c8a82;
}

.history-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.history-delete {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid rgba(29, 42, 38, 0.14);
  border-radius: 6px;
  background: rgba(197, 106, 71, 0.1);
  color: #a84d38;
  cursor: pointer;
  flex: none;
  transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.history-delete:hover:not(:disabled) {
  background: rgba(197, 106, 71, 0.2);
  border-color: rgba(197, 106, 71, 0.42);
  color: #8f3f2d;
}

.history-delete:disabled {
  cursor: wait;
  opacity: 0.7;
}

.memory-card {
  border-top: 1px solid rgba(29, 42, 38, 0.12);
  margin-top: 14px;
  padding-top: 14px;
}

.memory-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  color: #24453c;
}

.memory-head strong {
  font-family: var(--font-display);
  font-size: 17px;
}

.memory-head small {
  margin-left: auto;
  color: #7c8a82;
  font-size: 12px;
}

.memory-add {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.memory-add input {
  flex: 1;
  min-width: 0;
}

.memory-add .icon-btn {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex: none;
  padding: 0;
  border: 1px solid rgba(29, 42, 38, 0.16);
  border-radius: 6px;
  background: #fffdf5;
  color: #1c4b40;
  cursor: pointer;
}

.memory-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.memory-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 9px;
  border: 1px solid rgba(197, 106, 71, 0.28);
  border-radius: 999px;
  background: rgba(197, 106, 71, 0.08);
  color: #a84d38;
  font-size: 12px;
  cursor: pointer;
}

.memory-tag svg {
  flex: none;
}

.memory-save {
  width: 100%;
  margin-top: 12px;
}

.chat-panel {
  min-height: calc(100vh - 88px);
  grid-template-rows: auto 1fr auto;
}

.chat-head {
  display: grid;
  gap: 6px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(29, 42, 38, 0.12);
}

.chat-head .eyebrow {
  color: #c56a47;
}

.chat-head h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 26px;
}

.chat-head p {
  margin: 0;
  color: #5c6a63;
  font-size: 13px;
  line-height: 1.7;
}

.chat-head-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.chat-head-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.chat-new-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 6px 10px;
  border: 1px solid rgba(29, 42, 38, 0.16);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.72);
  color: #2e3d38;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.18s ease, background 0.18s ease, transform 0.18s ease;
}

.chat-new-btn:hover:not(:disabled) {
  border-color: rgba(197, 106, 71, 0.42);
  background: #ffffff;
  transform: translateY(-1px);
}

.chat-new-btn:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.chat-head-actions .chat-close {
  position: static;
  width: 34px;
  height: 34px;
  border-radius: 6px;
}

.chat-session-bar {
  display: flex;
}

.chat-history-toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  max-width: 100%;
  padding: 6px 9px;
  border: 1px solid rgba(29, 42, 38, 0.12);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.55);
  color: #2e3d38;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease;
}

.chat-history-toggle span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-history-toggle small {
  color: #7c8a82;
  font-weight: 600;
}

.chat-history-toggle.open {
  border-color: rgba(197, 106, 71, 0.4);
  background: #ffffff;
}

.chat-history-list {
  display: grid;
  gap: 6px;
  max-height: 240px;
  overflow-y: auto;
  padding: 4px;
  margin: -2px -4px 0;
}

.chat-session-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 2px 8px;
  padding: 8px 9px;
  border: 1px solid rgba(29, 42, 38, 0.12);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.6);
  color: #1f2933;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease;
}

.chat-session-item:hover,
.chat-session-item.active {
  border-color: rgba(197, 106, 71, 0.42);
  background: #ffffff;
}

.chat-session-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 700;
}

.chat-session-item small {
  color: #7c8a82;
  font-size: 11px;
}

.chat-session-delete {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid rgba(29, 42, 38, 0.14);
  border-radius: 6px;
  background: rgba(197, 106, 71, 0.1);
  color: #a84d38;
  cursor: pointer;
  grid-row: 1 / span 2;
  grid-column: 2;
  transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.chat-session-delete:hover {
  background: rgba(197, 106, 71, 0.2);
  border-color: rgba(197, 106, 71, 0.42);
  color: #8f3f2d;
}

.chat-history-error,
.chat-history-empty {
  margin: 2px 0;
  color: #7c8a82;
  font-size: 12px;
  line-height: 1.6;
}

.chat-history-error {
  color: #a84d38;
}

.chat-messages {
  min-height: 320px;
  overflow-y: auto;
  display: grid;
  align-content: start;
  gap: 8px;
  padding-right: 4px;
  scrollbar-color: rgba(28, 75, 64, 0.3) transparent;
}

.chat-msg {
  padding: 9px 11px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  box-shadow: 0 4px 12px rgba(16, 35, 31, 0.06);
}

.chat-msg.user {
  background: linear-gradient(135deg, #1c4b40, #2f6f5d);
  color: #fffaf0;
  justify-self: end;
  max-width: 88%;
  border-bottom-right-radius: 3px;
}

.chat-msg.assistant {
  background: rgba(255, 255, 255, 0.8);
  color: #1f2933;
  justify-self: start;
  max-width: 88%;
  border-bottom-left-radius: 3px;
}

.chat-msg.typing {
  display: flex;
  gap: 5px;
  align-items: center;
  padding: 14px 12px;
  min-width: 58px;
}

.chat-msg.typing span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #2f6f5d;
  animation: dotPulse 1.1s ease-in-out infinite;
}

.chat-msg.typing span:nth-child(2) {
  animation-delay: 0.15s;
}

.chat-msg.typing span:nth-child(3) {
  animation-delay: 0.3s;
}

.chat-input {
  display: flex;
  gap: 8px;
}

.chat-input input {
  flex: 1;
  min-height: 44px;
  padding: 10px 12px;
  border: 1px solid rgba(29, 42, 38, 0.18);
  border-radius: 6px;
  font-size: 14px;
}

.chat-input button {
  min-height: 44px;
  padding: 10px 15px;
  background: #c56a47;
  color: #ffffff;
  font-size: 14px;
  white-space: nowrap;
}

.reveal {
  opacity: 0;
  transform: translateY(18px);
  transition: opacity 0.45s ease, transform 0.45s ease;
}

.reveal.in-view {
  opacity: 1;
  transform: none;
}

.spin {
  animation: spin 1s linear infinite;
}

button:focus-visible,
input:focus-visible {
  outline: 3px solid rgba(197, 106, 71, 0.42);
  outline-offset: 2px;
}

@keyframes heroDrift {
  from {
    transform: scale(1.06) translate3d(-8px, var(--parallax-y, 0px), 0);
  }
  to {
    transform: scale(1.11) translate3d(12px, calc(var(--parallax-y, 0px) - 12px), 0);
  }
}

@keyframes riseIn {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes shimmer {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(100%);
  }
}

@keyframes dotPulse {
  0%,
  100% {
    transform: translateY(0);
    opacity: 0.5;
  }
  50% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1180px) {
  .planner {
    grid-template-columns: minmax(240px, 300px) 1fr;
  }

  .chat-panel {
    grid-column: 1 / -1;
    min-height: 460px;
    position: static;
  }
}

@media (max-width: 820px) {
  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .planner {
    grid-template-columns: 1fr;
    padding: 12px 14px 24px;
  }

  .info-panel,
  .chat-panel {
    position: static;
    max-height: none;
  }

  .hero,
  .hero-overlay {
    min-height: 360px;
  }

  .hero-overlay {
    padding: 28px;
  }

  .hero-overlay h2 {
    font-size: 42px;
  }

  .quick-grid {
    grid-template-columns: 1fr;
  }

  .map {
    height: 360px;
  }
}

@media (max-width: 640px) {
  .topbar {
    padding: 18px 16px 8px;
  }

  .topbar-meta {
    width: 100%;
    flex-wrap: wrap;
  }

  .planner {
    padding: 10px 12px 22px;
    gap: 14px;
  }

  .hero,
  .hero-overlay {
    min-height: 300px;
  }

  .hero-overlay {
    padding: 22px;
  }

  .hero-overlay h2 {
    font-size: 32px;
  }

  .hero-overlay p {
    font-size: 14px;
  }

  .result {
    padding: 18px;
  }

  .map {
    height: 300px;
  }

  .map-tools {
    align-items: stretch;
    flex-direction: column;
  }

  .chat-messages {
    min-height: 250px;
  }

  .row {
    grid-template-columns: 1fr;
  }

  .glass-panel {
    padding: 14px;
  }

  .day {
    padding: 18px 0;
  }

  .empty {
    min-height: 300px;
  }

  .empty h2 {
    font-size: 30px;
  }
}

/* Editorial magazine layout */
.page {
  background:
    radial-gradient(circle at 14% 10%, rgba(224, 164, 88, 0.1), transparent 30%),
    radial-gradient(circle at 86% 4%, rgba(82, 121, 138, 0.12), transparent 26%),
    #0e211c;
}

.topbar {
  max-width: 1760px;
  margin: 0 auto;
  padding: 20px 32px 12px;
  width: 100%;
}

.planner {
  grid-template-columns: minmax(260px, 300px) minmax(600px, 1fr) minmax(280px, 320px);
  gap: 24px;
  max-width: 1760px;
  padding: 18px 30px 38px;
}

.glass-panel {
  background: rgba(15, 34, 29, 0.92);
  border: 1px solid rgba(255, 245, 225, 0.14);
  box-shadow: 0 26px 70px rgba(3, 12, 9, 0.34);
  backdrop-filter: blur(22px) saturate(1.08);
}

.info-panel,
.chat-panel {
  border-radius: 4px;
  padding: 18px;
  color: #f6efdf;
}

.info-panel label,
.info-panel .field,
.info-panel .history h3,
.chat-head p {
  color: rgba(246, 239, 223, 0.86);
}

.info-panel input,
.chat-input input {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #fffaf0;
}

.info-panel input::placeholder,
.chat-input input::placeholder {
  color: rgba(246, 239, 223, 0.48);
}

.info-panel .options button,
.info-panel .segmented button,
.history-item {
  background: rgba(255, 255, 255, 0.07);
  border-color: rgba(255, 255, 255, 0.16);
  color: #f6efdf;
}

.info-panel .options button:hover,
.info-panel .segmented button:hover,
.history-item:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(224, 164, 88, 0.5);
}

.info-panel .options button.active,
.info-panel .segmented button.active {
  background: #c2573c;
  border-color: #c2573c;
  color: #ffffff;
}

.info-panel .submit {
  background: linear-gradient(135deg, #c2573c, #9d3f2d);
}

.info-panel .panel-cover {
  min-height: 210px;
  border-radius: 4px;
}

.info-panel .panel-cover strong {
  font-size: 30px;
}

.info-panel .history {
  border-color: rgba(255, 245, 225, 0.14);
}

.info-panel .memory-head strong {
  color: #f6efdf;
}

.info-panel .memory-head small {
  color: rgba(246, 239, 223, 0.62);
}

.info-panel .memory-add .icon-btn {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #fffaf0;
}

.info-panel .memory-tag {
  background: rgba(224, 164, 88, 0.14);
  border-color: rgba(224, 164, 88, 0.4);
  color: #ffe7c7;
}

.history-main,
.history-item small {
  color: rgba(246, 239, 223, 0.78);
}

.info-panel .history-delete {
  background: rgba(224, 164, 88, 0.12);
  border-color: rgba(255, 245, 225, 0.2);
  color: #f2c98f;
}

.info-panel .history-delete:hover:not(:disabled) {
  background: rgba(224, 164, 88, 0.24);
  border-color: rgba(224, 164, 88, 0.52);
  color: #fff0d6;
}

.loading-board {
  background: rgba(255, 253, 247, 0.94);
  border: 1px solid rgba(23, 58, 49, 0.14);
  border-radius: 4px;
  color: #2e3d38;
}

.canvas {
  background:
    linear-gradient(rgba(246, 239, 226, 0.96), rgba(246, 239, 226, 0.96)),
    url("https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1200&q=60") center / cover;
  border: 1px solid rgba(255, 245, 225, 0.1);
  border-radius: 4px;
  padding: 18px;
  box-shadow: 0 36px 90px rgba(3, 12, 9, 0.36);
}

.hero {
  min-height: 430px;
  border-radius: 4px;
}

.hero-overlay {
  min-height: 430px;
  padding: 38px 42px;
}

.result {
  display: grid;
  gap: 24px;
  padding: 26px 6px 10px;
  background: transparent;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.result-head {
  align-items: end;
  margin: 0;
  padding: 0 0 20px;
  border-bottom: 1px solid rgba(23, 58, 49, 0.16);
}

.masthead h2 {
  margin: 6px 0 0;
  font-size: 34px;
}

.overview {
  max-width: 860px;
  margin: 0;
  padding-left: 20px;
  border-left: 3px solid #c2573c;
  font-family: var(--font-display);
  font-size: 20px;
  line-height: 1.9;
  color: #334b42;
}

.quick-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 0;
}

.mini-card {
  min-height: 112px;
  border: 1px solid rgba(23, 58, 49, 0.14);
  border-top: 3px solid #c2573c;
  border-radius: 0;
  background: rgba(255, 253, 247, 0.72);
}

.mini-card::before {
  display: none;
}

.mini-card:nth-child(2) {
  border-top-color: #2f6f5d;
}

.mini-card:nth-child(3) {
  border-top-color: #52798a;
}

.atlas-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 230px;
  gap: 16px;
  align-items: stretch;
}

.map-stage {
  background: #173a31;
  border: 1px solid rgba(255, 245, 225, 0.14);
  border-radius: 4px;
  color: #f6efdf;
  margin: 0;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.day-tabs button {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: #f6efdf;
}

.day-tabs button:hover {
  background: rgba(255, 255, 255, 0.14);
  color: #ffffff;
}

.day-tabs button.active {
  background: #e0a458;
  border-color: #e0a458;
  color: #173a31;
}

.play-btn {
  background: #c2573c;
}

.route-legend span {
  color: rgba(246, 239, 223, 0.8);
}

.route-legend i {
  border-radius: 0;
}

.route-progress {
  color: #f2d9b4;
}

.map {
  background: #e7efe8;
}

.dossier {
  display: grid;
  align-content: start;
  gap: 16px;
}

.featured-day {
  padding: 18px 16px;
  border: 1px solid rgba(23, 58, 49, 0.14);
  border-left: 3px solid #2f6f5d;
  border-radius: 0;
  background: rgba(255, 253, 247, 0.72);
}

.featured-day h3 {
  font-size: 22px;
}

.dossier .adjust {
  display: grid;
  gap: 8px;
  margin: 0;
}

.dossier .adjust button {
  width: 100%;
}

.chapter-head {
  display: grid;
  gap: 6px;
  padding-top: 24px;
  border-top: 1px solid rgba(23, 58, 49, 0.16);
}

.chapter-head h3 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 28px;
}

.chapters {
  display: grid;
}

.day {
  grid-template-columns: 86px minmax(0, 1fr);
  gap: 20px;
  padding: 32px 0;
  margin: 0;
}

.chapter-no {
  font-family: var(--font-display);
  font-size: 62px;
  line-height: 0.9;
  color: rgba(194, 87, 60, 0.16);
  -webkit-text-stroke: 1.5px #c2573c;
  user-select: none;
}

.chapter-body {
  min-width: 0;
}

.chapter-body h3 {
  margin: 2px 0 16px;
  font-size: 22px;
}

.day-weather {
  display: grid;
  gap: 6px;
  margin: 12px 0;
  padding: 10px 12px;
  border-left: 3px solid #d99a3d;
  border-radius: 4px;
  background: linear-gradient(135deg, rgba(255, 253, 245, 0.96), rgba(241, 247, 242, 0.92));
  color: #2e3d38;
}

.day-weather-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.day-weather-head span {
  color: #7c8a82;
  font-size: 11px;
  font-weight: 700;
}

.day-weather-head strong {
  color: #1c4b40;
  font-size: 15px;
}

.day-weather-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  color: #4d5c55;
  font-size: 12px;
  font-weight: 700;
}

.day-weather small {
  color: #a84d38;
  font-size: 12px;
  line-height: 1.45;
}

@media (max-width: 640px) {
  .day-weather-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }
}
.spots {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.foods {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.spot,
.food,
.hotel-item {
  border-radius: 2px;
}

.backmatter {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 30px 42px;
  padding: 28px 0 8px;
  border-top: 1px solid rgba(23, 58, 49, 0.16);
}

.budget,
.hotel,
.nearby,
.notes {
  border: 0;
  margin: 0;
  padding: 0;
}

.budget h3,
.hotel h3,
.nearby h3,
.notes h3 {
  font-size: 18px;
}

.chat-head .eyebrow {
  color: #e0a458;
}

.chat-head h2 {
  color: #f6efdf;
}

.chat-msg.assistant {
  background: rgba(255, 255, 255, 0.09);
  color: #f6efdf;
}

.chat-msg.user {
  background: linear-gradient(135deg, #c2573c, #9d3f2d);
  color: #fffaf0;
}

.chat-input button {
  background: #e0a458;
  color: #173a31;
}

.chat-input button:hover:not(:disabled) {
  background: #f0b76a;
  color: #173a31;
}

.chat-head {
  border-color: rgba(255, 245, 225, 0.14);
}

.chat-new-btn {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 245, 225, 0.2);
  color: #f6efdf;
}

.chat-new-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(224, 164, 88, 0.5);
  color: #fffaf0;
}

.chat-history-toggle {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 245, 225, 0.18);
  color: #f6efdf;
}

.chat-history-toggle small {
  color: rgba(246, 239, 223, 0.62);
}

.chat-history-toggle.open {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(224, 164, 88, 0.52);
  color: #fffaf0;
}

.chat-session-item {
  background: rgba(255, 255, 255, 0.07);
  border-color: rgba(255, 245, 225, 0.16);
  color: #f6efdf;
}

.chat-session-item:hover,
.chat-session-item.active {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(224, 164, 88, 0.5);
  color: #fffaf0;
}

.chat-session-item small {
  color: rgba(246, 239, 223, 0.62);
}

.chat-session-delete {
  background: rgba(224, 164, 88, 0.12);
  border-color: rgba(255, 245, 225, 0.2);
  color: #f2c98f;
}

.chat-session-delete:hover {
  background: rgba(224, 164, 88, 0.24);
  border-color: rgba(224, 164, 88, 0.52);
  color: #fff0d6;
}

.chat-history-error,
.chat-history-empty {
  color: rgba(246, 239, 223, 0.62);
}

.chat-history-error {
  color: #f2a58a;
}

@media (max-width: 1360px) {
  .planner {
    grid-template-columns: minmax(250px, 290px) minmax(520px, 1fr);
  }

  .chat-panel {
    grid-column: 1 / -1;
    min-height: 470px;
    position: static;
  }

  .atlas-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .dossier {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 900px) {
  .planner {
    grid-template-columns: 1fr;
    padding: 12px 16px 28px;
  }

  .info-panel,
  .chat-panel {
    position: static;
    max-height: none;
  }

  .hero,
  .hero-overlay {
    min-height: 360px;
  }

  .quick-grid,
  .backmatter,
  .dossier {
    grid-template-columns: 1fr;
  }

  .atlas-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  .topbar {
    padding: 18px 16px 8px;
  }

  .planner {
    padding: 10px 12px 22px;
  }

  .canvas {
    padding: 12px;
  }

  .hero,
  .hero-overlay {
    min-height: 310px;
  }

  .hero-overlay {
    padding: 22px;
  }

  .hero-overlay h2 {
    font-size: 32px;
  }

  .result {
    padding: 20px 4px 8px;
    gap: 20px;
  }

  .result-head {
    align-items: start;
  }

  .masthead h2 {
    font-size: 28px;
  }

  .overview {
    font-size: 17px;
    padding-left: 14px;
  }

  .map {
    height: 300px;
  }

  .day {
    grid-template-columns: 1fr;
    gap: 12px;
    padding: 24px 0;
  }

  .chapter-no {
    font-size: 44px;
  }

  .spots,
  .foods {
    grid-template-columns: 1fr;
  }

  .map-tools {
    align-items: stretch;
    flex-direction: column;
  }
}


/* Full-bleed drawer workspace */
.topbar {
  position: sticky;
  top: 0;
  z-index: 90;
  max-width: none;
  margin: 0;
  padding: 14px 30px;
  background: rgba(14, 33, 28, 0.9);
  border-bottom: 1px solid rgba(255, 245, 225, 0.12);
  backdrop-filter: blur(20px) saturate(1.1);
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}

.topbar-meta {
  margin-right: 4px;
}

.tool-btn {
  min-height: 44px;
  padding: 0 15px;
  border: 1px solid rgba(255, 245, 225, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  color: #f6efdf;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, transform 0.2s ease, color 0.2s ease;
}

.tool-btn:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(224, 164, 88, 0.55);
}

.tool-btn.active {
  background: #c2573c;
  border-color: #c2573c;
  color: #ffffff;
}

.planner {
  display: block;
  max-width: 1640px;
  margin: 0 auto;
  padding: 24px 32px 44px;
}

.canvas {
  max-width: 1480px;
  margin: 0 auto;
}

.hero {
  min-height: 500px;
}

.hero-overlay {
  min-height: 500px;
  padding: 44px 48px;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  animation: riseIn 0.6s ease both;
  animation-delay: 0.28s;
}

.hero-cta {
  min-height: 48px;
  padding: 0 18px;
  border: 0;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: #e0a458;
  color: #173a31;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 14px 30px rgba(0, 0, 0, 0.22);
  transition: transform 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
}

.hero-cta:hover {
  transform: translateY(-2px);
  background: #f0b76a;
}

.hero-cta.ghost {
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: #fffaf0;
  box-shadow: none;
}

.hero-cta.ghost:hover {
  background: rgba(255, 255, 255, 0.2);
}

.info-panel,
.chat-panel {
  position: fixed;
  top: 78px;
  bottom: 16px;
  width: min(400px, calc(100vw - 32px));
  max-height: none;
  min-height: 0;
  overflow: hidden;
  z-index: 80;
  border-radius: 4px;
  opacity: 0;
  pointer-events: none;
  transform: translateY(12px);
  transition: transform 0.32s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.24s ease;
  box-shadow: 0 36px 90px rgba(0, 0, 0, 0.46);
}

.info-panel {
  left: 16px;
  overflow-y: auto;
  transform: translateX(calc(-100% - 32px));
}

.chat-panel {
  right: 16px;
  display: grid;
  grid-template-rows: auto 1fr auto;
  overflow: hidden;
  transform: translateX(calc(100% + 32px));
}

.page.info-open .info-panel,
.page.chat-open .chat-panel {
  opacity: 1;
  pointer-events: auto;
  transform: translateX(0);
}

.drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 70;
  background: rgba(4, 12, 9, 0.46);
  backdrop-filter: blur(4px);
  animation: fadeIn 0.22s ease both;
}

.drawer-close {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 3;
  width: 40px;
  height: 40px;
  padding: 0;
  display: grid;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.24);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
  color: #f6efdf;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease;
}

.drawer-close:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: rotate(90deg);
}

.panel-cover {
  position: relative;
}

.chat-head {
  position: relative;
  padding-right: 44px;
}

.chat-close {
  top: 0;
  right: 0;
  background: rgba(255, 255, 255, 0.08);
}

.atlas-grid {
  grid-template-columns: minmax(0, 1fr) 260px;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@media (max-width: 1100px) {
  .topbar {
    padding: 12px 18px;
  }

  .topbar-actions {
    gap: 8px;
  }

  .topbar-meta {
    display: none;
  }

  .planner {
    padding: 18px 18px 34px;
  }

  .atlas-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .dossier {
    grid-template-columns: 1fr 1fr;
  }

  .info-panel,
  .chat-panel {
    top: 68px;
    bottom: 10px;
  }
}

@media (max-width: 720px) {
  .topbar {
    flex-wrap: wrap;
    gap: 10px;
  }

  .topbar-actions {
    width: 100%;
  }

  .tool-btn {
    flex: 1;
  }

  .hero,
  .hero-overlay {
    min-height: 340px;
  }

  .hero-overlay {
    padding: 24px;
  }

  .hero-overlay h2 {
    font-size: 32px;
  }

  .planner {
    padding: 12px 12px 26px;
  }

  .canvas {
    padding: 12px;
  }

  .info-panel,
  .chat-panel {
    top: auto;
    left: 10px;
    right: 10px;
    bottom: 10px;
    width: auto;
    max-height: calc(100vh - 20px);
  }

  .info-panel {
    transform: translateY(calc(100% + 20px));
  }

  .chat-panel {
    transform: translateY(calc(100% + 20px));
  }

  .page.info-open .info-panel,
  .page.chat-open .chat-panel {
    transform: translateY(0);
  }

  .dossier {
    grid-template-columns: 1fr;
  }
}


/* Rotating canvas imagery */
.hero-fade-enter-active,
.hero-fade-leave-active {
  transition: opacity 0.9s ease;
}

.hero-fade-enter-from,
.hero-fade-leave-to {
  opacity: 0;
}

.hero-bg {
  will-change: opacity, transform;
}

.hero-slides {
  position: absolute;
  right: 24px;
  bottom: 20px;
  z-index: 4;
  display: flex;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 999px;
  background: rgba(10, 24, 20, 0.36);
  backdrop-filter: blur(10px);
}

.hero-slides button {
  width: 10px;
  height: 10px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  transition: width 0.25s ease, background 0.25s ease, transform 0.25s ease;
}

.hero-slides button:hover {
  transform: scale(1.2);
  background: rgba(255, 255, 255, 0.8);
}

.hero-slides button.active {
  width: 26px;
  background: #e0a458;
}

.canvas {
  background:
    linear-gradient(rgba(246, 239, 226, 0.92), rgba(246, 239, 226, 0.96)),
    var(--canvas-image, url("https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1200&q=60")) center / cover;
}


/* Balanced canvas image framing */
.hero {
  min-height: 480px;
  max-height: 600px;
  aspect-ratio: 21 / 9;
}

.hero-overlay {
  min-height: 480px;
  padding: 44px 48px;
}

.hero-bg {
  background:
    linear-gradient(90deg, rgba(13, 25, 22, 0.88), rgba(13, 25, 22, 0.2) 58%, rgba(13, 25, 22, 0.58)),
    var(--hero-image, url("https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?auto=format&fit=crop&w=1600&h=900&q=75")) center 32% / cover;
  background-position: center 32%;
}

.canvas {
  background:
    radial-gradient(circle at 8% 4%, rgba(224, 164, 88, 0.08), transparent 24%),
    linear-gradient(180deg, #faf4e8 0%, #f3ead8 100%);
}

@media (max-width: 1100px) {
  .hero,
  .hero-overlay {
    min-height: 430px;
  }
}

@media (max-width: 720px) {
  .hero,
  .hero-overlay {
    min-height: 340px;
    max-height: 420px;
    aspect-ratio: auto;
  }

  .hero-overlay {
    padding: 24px;
  }

  .hero-overlay h2 {
    font-size: 30px;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }

  .reveal {
    opacity: 1 !important;
    transform: none !important;
  }

  .hero-bg {
    animation: none;
    transform: none;
  }
}

.export-btn {
  min-height: 44px;
  padding: 8px 13px;
  border: 1px solid rgba(23, 58, 49, 0.16);
  border-radius: 6px;
  background: #fffdf5;
  color: #173a31;
  font-size: 13px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.export-btn:hover {
  transform: translateY(-1px);
  border-color: #c2573c;
  background: #fff8ea;
}

.share-card {
  position: fixed;
  left: -9999px;
  top: 0;
  width: 1200px;
  min-height: 630px;
  padding: 48px;
  background: #f6efe2;
  color: #173a31;
  font-family: var(--font-body);
}

.share-card h2 {
  margin: 12px 0;
  font-family: var(--font-display);
  font-size: 52px;
}

.share-card p {
  max-width: 900px;
  font-size: 18px;
  line-height: 1.8;
  color: #4d5c55;
}

.share-card > div {
  display: grid;
  gap: 6px;
  margin-top: 24px;
  padding: 16px;
  border-left: 3px solid #c2573c;
  background: #fffdf5;
}

.share-card small {
  display: block;
  margin-top: 28px;
  color: #7c8a82;
}

.variant-bar {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin: 0 0 16px;
}

.variant-option {
  display: grid;
  gap: 4px;
  min-height: 96px;
  padding: 14px 16px;
  border: 1px solid rgba(29, 42, 38, 0.14);
  border-radius: 8px;
  background: #fffdf5;
  color: #2e3d38;
  text-align: left;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(16, 35, 31, 0.06);
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.variant-option:hover {
  transform: translateY(-2px);
  border-color: rgba(197, 106, 71, 0.45);
  box-shadow: 0 12px 24px rgba(16, 35, 31, 0.1);
}

.variant-option.active {
  border-color: #c56a47;
  background: linear-gradient(135deg, #fffaf0, #f7e8d8);
  box-shadow: inset 0 0 0 1px rgba(197, 106, 71, 0.28), 0 12px 26px rgba(168, 77, 56, 0.14);
}

.variant-name {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  color: #1c4b40;
}

.variant-option.active .variant-name {
  color: #a84d38;
}

.variant-option strong {
  font-size: 20px;
  color: #1c4b40;
}

.variant-option small {
  color: #7c8a82;
}

@media (max-width: 640px) {
  .variant-bar {
    grid-template-columns: 1fr;
  }

  .variant-option {
    min-height: 84px;
  }
}

.play-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.speed-seg {
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  border: 1px solid rgba(29, 42, 38, 0.14);
  border-radius: 999px;
  background: #fffdf5;
}

.speed-seg button {
  min-width: 38px;
  min-height: 34px;
  padding: 0 10px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #5c6a63;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.speed-seg button.active {
  background: #1c4b40;
  color: #fffaf0;
}

.stop-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid rgba(179, 38, 30, 0.28);
  border-radius: 6px;
  background: #fff5f2;
  color: #b3261e;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

.featured-points button {
  padding: 7px 10px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: #e7f2eb;
  color: #1c4b40;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.featured-points button:hover {
  transform: translateY(-1px);
  border-color: rgba(197, 106, 71, 0.4);
}

.featured-points button.active {
  background: #c56a47;
  border-color: #c56a47;
  color: #ffffff;
}

.spot,
.food {
  cursor: pointer;
}

.spot.active,
.food.active {
  border-color: #c56a47;
  background: #fff7ee;
  box-shadow: inset 0 0 0 1px rgba(197, 106, 71, 0.35), 0 16px 32px rgba(168, 77, 56, 0.12);
}

.budget-detail {
  display: grid;
  gap: 18px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid rgba(29, 42, 38, 0.1);
}

.budget-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.budget-summary-block {
  padding: 11px 12px;
  border: 1px solid rgba(29, 42, 38, 0.08);
  border-radius: 6px;
  background: #f1f7f2;
}

.budget-summary-block > span {
  display: block;
  color: #4d5c55;
  font-size: 12px;
  font-weight: 700;
}

.budget-summary-block strong {
  display: block;
  margin-top: 3px;
  color: #1c4b40;
  font-size: 17px;
}

.budget-summary-block small {
  display: block;
  margin-top: 3px;
  color: #7c8a82;
  font-size: 11px;
  line-height: 1.4;
}

.budget-summary-block.actual {
  background: #fff3e8;
  border-color: rgba(197, 106, 71, 0.22);
}

.budget-summary-block.actual strong {
  color: #a84d38;
}

.budget-summary-block.under {
  background: #eef6ef;
  border-color: rgba(47, 111, 93, 0.25);
}

.budget-summary-block.over {
  background: #fff0ee;
  border-color: rgba(179, 38, 30, 0.25);
}

.budget-compare {
  display: grid;
  gap: 6px;
}

.budget-compare-track {
  position: relative;
  height: 10px;
  border-radius: 999px;
  background: #e7efe8;
}

.budget-compare-range {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: 999px;
  background: rgba(47, 111, 93, 0.35);
  border: 1px solid rgba(47, 111, 93, 0.55);
}

.budget-compare.over .budget-compare-range {
  background: rgba(179, 38, 30, 0.28);
  border-color: rgba(179, 38, 30, 0.5);
}

.budget-compare-dot {
  position: absolute;
  top: 50%;
  width: 16px;
  height: 16px;
  border: 3px solid #ffffff;
  border-radius: 50%;
  background: #a84d38;
  box-shadow: 0 2px 8px rgba(29, 42, 38, 0.28);
  transform: translate(-50%, -50%);
}

.budget-compare-labels {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 12px;
  color: #7c8a82;
  font-size: 11px;
}

.budget-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.budget-toolbar-title {
  color: #2e3d38;
  font-size: 14px;
  font-weight: 800;
}

.budget-save-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 13px;
  border: 1px solid rgba(197, 106, 71, 0.35);
  border-radius: 6px;
  background: #fff3e8;
  color: #a84d38;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
  transition: background 0.16s ease, transform 0.16s ease;
}

.budget-save-btn:hover:not(:disabled) {
  background: #c56a47;
  color: #ffffff;
}

.budget-save-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.budget-save-note {
  margin: 0;
  color: #1c4b40;
  font-size: 12px;
  font-weight: 700;
}

.budget-ledger {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
}

.ledger-nav {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  overflow-x: auto;
  scrollbar-width: none;
}

.ledger-nav::-webkit-scrollbar {
  display: none;
}

.ledger-day-tab {
  flex: 0 0 auto;
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid rgba(29, 42, 38, 0.14);
  border-radius: 999px;
  background: rgba(255, 253, 245, 0.72);
  color: #2e3d38;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease, border-color 0.16s ease, transform 0.16s ease;
}

.ledger-day-tab:hover {
  border-color: rgba(197, 106, 71, 0.42);
  transform: translateY(-1px);
}

.ledger-day-tab.active {
  border-color: #c56a47;
  background: #c56a47;
  color: #ffffff;
}

.ledger-card {
  grid-area: 1 / 1;
  min-width: 0;
  transform: translate3d(var(--stack-x, 0px), 0, 0) scale(var(--stack-scale, 1)) rotate(var(--stack-rotate, 0deg));
  opacity: var(--stack-opacity, 0);
  z-index: var(--stack-z, 0);
  pointer-events: none;
  will-change: transform, opacity;
  transition: transform 0.42s cubic-bezier(0.22, 0.8, 0.28, 1), opacity 0.32s ease, box-shadow 0.42s ease;
}

.ledger-card.active {
  pointer-events: auto;
  box-shadow: 0 18px 38px rgba(29, 42, 38, 0.16);
}

.expense-list {
  display: grid;
  gap: 2px;
}

.expense-slide-enter-active,
.expense-slide-leave-active,
.expense-slide-move {
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.expense-slide-enter-from {
  transform: translateX(22px);
  opacity: 0;
}

.expense-slide-leave-to {
  transform: translateX(-22px);
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .ledger-card,
  .expense-slide-enter-active,
  .expense-slide-leave-active,
  .expense-slide-move {
    transition: none !important;
  }
}

.budget-day {
  display: grid;
  align-content: start;
  gap: 8px;
  padding: 14px;
  border: 1px solid rgba(29, 42, 38, 0.12);
  border-radius: 6px;
  background: #fffdf5;
}

.budget-day-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px dashed rgba(29, 42, 38, 0.16);
}

.budget-day-head span {
  color: #a84d38;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.budget-day-head strong {
  font-family: var(--font-display);
  font-size: 17px;
  color: #1c4b40;
  white-space: nowrap;
}

.expense-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas:
    "category range"
    "amount note";
  gap: 6px 10px;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px dashed rgba(29, 42, 38, 0.1);
}

.expense-row:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.expense-category {
  grid-area: category;
  color: #2e3d38;
  font-size: 13px;
  font-weight: 800;
}

.expense-range {
  grid-area: range;
  color: #7c8a82;
  font-size: 11px;
  line-height: 1.35;
  text-align: right;
}

.expense-row input[type="number"] {
  grid-area: amount;
}

.expense-row input[type="text"] {
  grid-area: note;
}

.expense-row input {
  width: 100%;
  min-width: 0;
  height: 34px;
  padding: 0 9px;
  border: 1px solid rgba(29, 42, 38, 0.18);
  border-radius: 5px;
  background: #ffffff;
  color: #1c4b40;
  font-size: 13px;
  font-family: var(--font-body);
  outline: none;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.expense-row input:focus {
  border-color: #c56a47;
  box-shadow: 0 0 0 3px rgba(197, 106, 71, 0.14);
}

.expense-row input::placeholder {
  color: #a5aea8;
}

.expense-row input.expense-category-input {
  grid-area: category;
  border-color: rgba(197, 106, 71, 0.32);
  background: #fffaf4;
  color: #a84d38;
  font-weight: 700;
}

.expense-row input.expense-category-input:focus {
  border-color: #c56a47;
  box-shadow: 0 0 0 3px rgba(197, 106, 71, 0.14);
}

.expense-remove {
  grid-area: range;
  justify-self: end;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid rgba(179, 38, 30, 0.22);
  border-radius: 50%;
  background: #fff5f2;
  color: #b3261e;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease;
}

.expense-remove:hover {
  background: #b3261e;
  color: #ffffff;
}

.expense-quick-add {
  display: grid;
  gap: 6px;
  padding-top: 6px;
}

.expense-quick-add > span {
  color: #7c8a82;
  font-size: 11px;
  font-weight: 700;
}

.expense-quick-add-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.expense-quick-add-buttons button {
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid rgba(29, 42, 38, 0.14);
  border-radius: 999px;
  background: #f1f7f2;
  color: #2e3d38;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease, border-color 0.16s ease;
}

.expense-quick-add-buttons button:hover {
  border-color: rgba(197, 106, 71, 0.45);
  background: #fff3e8;
  color: #a84d38;
}

.expense-quick-add-buttons button.custom {
  border-style: dashed;
  background: #fffaf4;
  color: #a84d38;
}

.budget-categories {
  display: grid;
  gap: 12px;
}

.budget-category {
  display: grid;
  gap: 7px;
}

.budget-category-head {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 10px;
  align-items: center;
  font-size: 13px;
  font-weight: 800;
}

.budget-category-head span {
  color: #2e3d38;
}

.budget-category-head strong {
  color: #1c4b40;
}

.budget-category-head i {
  min-width: 44px;
  padding: 3px 7px;
  border-radius: 999px;
  background: #e7f2eb;
  color: #1c4b40;
  font-size: 11px;
  font-style: normal;
  text-align: center;
}

.budget-track {
  height: 8px;
  border-radius: 999px;
  background: #e7efe8;
  overflow: hidden;
}

.budget-track span {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #2f6f5d, #c56a47);
}

.budget-note {
  color: #7c8a82;
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 640px) {
  .budget-summary {
    grid-template-columns: 1fr;
  }

  .budget-ledger {
    grid-template-columns: 1fr;
  }

  .budget-day-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .expense-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }
}

@media print {
  .topbar,
  .drawer-backdrop,
  .info-panel,
  .chat-panel,
  .hero,
  .map-stage,
  .adjust,
  .save,
  .export-btn,
  .play-controls,
  .variant-bar,
  .share-card {
    display: none !important;
  }

  .planner,
  .canvas,
  .result {
    max-width: 100% !important;
    padding: 0 !important;
    box-shadow: none !important;
    background: #ffffff !important;
  }

  .day,
  .backmatter {
    break-inside: avoid;
  }
}

</style>
