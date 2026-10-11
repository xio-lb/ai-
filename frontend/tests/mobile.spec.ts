import { test, expect, type Page } from '@playwright/test'

const viewports = [
  { name: '375', width: 375, height: 812 },
  { name: '390', width: 390, height: 844 },
  { name: '768', width: 768, height: 1024 },
  { name: '1024', width: 1024, height: 768 },
  { name: '1440', width: 1440, height: 900 }
]

const chatSessions = Array.from({ length: 5 }, (_, index) => ({
  id: index + 1,
  title: index === 0 ? '成都三日美食与人文' : `旅行计划 ${index + 1}`,
  created_at: '2026-10-01 10:00',
  updated_at: '2026-10-01 12:00',
  message_count: index + 2
}))

const planFixture = {
  destination: '成都',
  days: 2,
  budget: 3000,
  preferences: ['美食', '人文'],
  overview: '从宽窄巷子到武侯祠，用两天感受成都的慢节奏与烟火气。',
  daily_plans: [
    {
      day: 1,
      theme: '老城人文与街巷',
      spots: [
        {
          name: '宽窄巷子',
          address: '成都市青羊区金河路口',
          duration: '2 小时',
          description: '漫步川西民居街巷，体验成都慢生活。',
          location: '104.055,30.669'
        },
        {
          name: '武侯祠',
          address: '成都市武侯区武侯祠大街 231 号',
          duration: '2.5 小时',
          description: '了解三国文化与成都历史。',
          location: '104.047,30.646'
        }
      ],
      foods: [
        {
          name: '钟水饺',
          cuisine: '川味小吃',
          price_range: '30-60 元',
          address: '成都市青羊区人民公园附近',
          description: '成都经典小吃，适合安排午餐。',
          best_time: '12:00',
          location: '104.057,30.657'
        }
      ]
    },
    {
      day: 2,
      theme: '公园与市井生活',
      spots: [
        {
          name: '人民公园',
          address: '成都市青羊区少城路 12 号',
          duration: '2 小时',
          description: '在鹤鸣茶社体验盖碗茶与成都生活。',
          location: '104.058,30.657'
        }
      ],
      foods: [
        {
          name: '龙抄手',
          cuisine: '川味小吃',
          price_range: '40-80 元',
          address: '成都市锦江区春熙路附近',
          description: '适合作为返程前的最后一餐。',
          best_time: '18:00',
          location: '104.081,30.657'
        }
      ]
    }
  ],
  total_cost: 2860,
  notes: ['热门景点建议提前预约。'],
  budget_report: {
    budget: 3000,
    total_cost: 2860,
    within_budget: true,
    savings: 140,
    suggestions: ['餐饮选择本地小店可以进一步节省预算。']
  },
  budget_detail: {
    total_cost: 2860,
    budget: 3000,
    days: [
      { day: 1, amount: 1430, min_amount: 1200, max_amount: 1650, typical: 1430, categories: { 门票: 120, 餐饮: 180, 住宿: 700, 交通: 80, 其他: 350 } },
      { day: 2, amount: 1430, min_amount: 1200, max_amount: 1650, typical: 1430, categories: { 门票: 80, 餐饮: 180, 住宿: 700, 交通: 80, 其他: 390 } }
    ],
    categories: [
      { category: '门票', amount: 200, min_amount: 160, max_amount: 260, typical: 200, note: '按常规门票估算', items: [] },
      { category: '餐饮', amount: 360, min_amount: 280, max_amount: 480, typical: 360, note: '按本地餐饮估算', items: [] },
      { category: '住宿', amount: 1400, min_amount: 1000, max_amount: 2000, typical: 1400, note: '节假日可能上浮', items: [] },
      { category: '交通', amount: 160, min_amount: 100, max_amount: 260, typical: 160, note: '市区公共交通为主', items: [] },
      { category: '其他', amount: 740, min_amount: 400, max_amount: 1200, typical: 740, note: '含纪念品和临时支出', items: [] }
    ],
    actual_expenses: []
  },
  hotels: [
    {
      name: '成都太古里附近酒店',
      address: '成都市锦江区中纱帽街',
      location: '104.081,30.653',
      category: '舒适型',
      phone: '',
      price_hint: '约 700 元/晚'
    }
  ],
  weather: {
    city: '成都',
    weather: '多云',
    temperature: '22',
    wind_direction: '东南风',
    wind_power: '2 级',
    humidity: '68',
    report_time: '2026-10-11 10:00',
    forecasts: []
  },
  nearby: [],
  routes: {},
  route_legs: [
    {
      mode: 'walking',
      duration_seconds: 720,
      distance_meters: 900,
      duration_text: '12 分钟',
      distance_text: '900 米',
      polyline: '104.081,30.653;104.070,30.660;104.055,30.669',
      leg_key: 'd1:hotel->宽窄巷子',
      from_name: '成都太古里附近酒店',
      to_name: '宽窄巷子',
      from_location: '104.081,30.653',
      to_location: '104.055,30.669',
      day: 1,
      stop_type: 'spot'
    },
    {
      mode: 'driving',
      duration_seconds: 900,
      distance_meters: 2400,
      duration_text: '15 分钟',
      distance_text: '2.4 公里',
      polyline: '104.055,30.669;104.050,30.656;104.047,30.646',
      leg_key: 'd1:宽窄巷子->武侯祠',
      from_name: '宽窄巷子',
      to_name: '武侯祠',
      from_location: '104.055,30.669',
      to_location: '104.047,30.646',
      day: 1,
      stop_type: 'spot'
    },
    {
      mode: 'transit',
      duration_seconds: 960,
      distance_meters: 2600,
      duration_text: '16 分钟',
      distance_text: '2.6 公里',
      polyline: '104.047,30.646;104.050,30.652;104.081,30.653',
      leg_key: 'd1:武侯祠->hotel',
      from_name: '武侯祠',
      to_name: '成都太古里附近酒店',
      from_location: '104.047,30.646',
      to_location: '104.081,30.653',
      day: 1,
      stop_type: 'hotel'
    }
  ],
  transport_mode: 'auto',
  quality_report: {
    passed: true,
    issues: [],
    repairs: [],
    checked_at: '2026-10-11 10:00'
  }
}

async function preparePage(page: Page) {
  await page.addInitScript(() => {
    class FakeMap {
      constructor(container: HTMLElement) {
        container.dataset.amapReady = 'true'
      }
      add() {}
      remove() {}
      destroy() {}
      setFitView() {}
      setCenter() {}
    }
    class FakeMarker {
      private position: unknown
      constructor(options: { position: unknown }) {
        this.position = options.position
      }
      on() {
        return this
      }
      getPosition() {
        return this.position
      }
      setPosition(position: unknown) {
        this.position = position
      }
    }
    class FakePolyline {
      setOptions() {}
    }
    class FakeInfoWindow {
      open() {}
    }
    ;(window as any).AMap = {
      Map: FakeMap,
      Marker: FakeMarker,
      Polyline: FakePolyline,
      InfoWindow: FakeInfoWindow
    }
  })

  await page.route('https://images.unsplash.com/**', (route) => route.abort())
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (path === '/api/history' && request.method() === 'GET') {
      await route.fulfill({ json: [] })
      return
    }

    if (path === '/api/memory' && request.method() === 'GET') {
      await route.fulfill({
        json: {
          preferences: [],
          visited_cities: [],
          dietary_notes: '',
          pace: '',
          transport_mode: '',
          hotel_budget: 0,
          companions: 1,
          updated_at: ''
        }
      })
      return
    }

    if (path === '/api/chat/sessions' && request.method() === 'GET') {
      await route.fulfill({ json: chatSessions })
      return
    }

    if (path === '/api/chat' && request.method() === 'POST') {
      await route.fulfill({
        json: {
          session_id: 1,
          reply: '已收到你的旅行需求，我会继续帮你补全。',
          ready: false,
          trip_request: null
        }
      })
      return
    }

    if (path === '/api/trip/plan/stream' && request.method() === 'POST') {
      const body = `event: done\ndata: ${JSON.stringify(planFixture)}\n\n`
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream; charset=utf-8',
        body
      })
      return
    }

    await route.fulfill({ json: {} })
  })
}

async function expectNoHorizontalOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth
  }))

  expect(metrics.document).toBeLessThanOrEqual(metrics.viewport + 1)
  expect(metrics.body).toBeLessThanOrEqual(metrics.viewport + 1)
}

async function expectElementInsideViewport(page: Page, selector: string, requireVertical = true) {
  const box = await page.locator(selector).boundingBox()
  const viewport = page.viewportSize()
  expect(box).not.toBeNull()
  expect(viewport).not.toBeNull()
  if (!box || !viewport) return

  expect(box.x).toBeGreaterThanOrEqual(-1)
  expect(box.y).toBeGreaterThanOrEqual(-1)
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1)
  if (requireVertical) {
    expect(box.y + box.height).toBeLessThanOrEqual(viewport.height + 1)
  }
}

async function expectKeyTextFits(page: Page) {
  const clipped = await page
    .locator('.brand h1, .tool-btn, .hero-overlay h2, .hero-overlay p, .hero-cta')
    .evaluateAll((elements) =>
      elements
        .filter((element) => {
          const style = getComputedStyle(element)
          const rect = element.getBoundingClientRect()
          return (
            rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== 'hidden' &&
            style.opacity !== '0' &&
            element.scrollWidth > element.clientWidth + 1
          )
        })
        .map((element) => element.textContent?.trim() || element.className)
    )

  expect(clipped).toEqual([])
}

test.describe('移动端核心界面', () => {
  for (const viewport of viewports) {
    test(`${viewport.name}px：布局、抽屉、聊天与账号弹窗`, async ({ page }) => {
      await preparePage(page)
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto('/')

      await expect(page.getByRole('button', { name: '行程资料', exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: '生成行程', exact: true })).toBeVisible()
      await expectNoHorizontalOverflow(page)
      await expectKeyTextFits(page)

      await page.getByRole('button', { name: '行程资料', exact: true }).click()
      await expect(page.locator('.info-panel')).toHaveCSS('opacity', '1')
      await expectElementInsideViewport(page, '.info-panel')
      await page.getByRole('button', { name: '关闭行程资料' }).click()

      await page.locator('header.topbar').getByRole('button', { name: 'AI 对话', exact: true }).click()
      await expect(page.locator('.chat-panel')).toHaveCSS('opacity', '1')
      await expectElementInsideViewport(page, '.chat-panel')

      await page.locator('.chat-history-toggle').click()
      await expect(page.locator('.chat-history-list')).toBeVisible()
      await expectElementInsideViewport(page, '.chat-panel')
      await expectNoHorizontalOverflow(page)

      await page.locator('.chat-input input').fill('帮我补充旅行需求')
      await page.getByRole('button', { name: '发送消息' }).click()
      await expect(page.locator('.chat-msg.assistant').last()).toContainText('已收到你的旅行需求')
      await expectElementInsideViewport(page, '.chat-panel')

      await page.getByRole('button', { name: '关闭AI对话' }).click()
      await page.locator('.account-btn').click()
      await expect(page.locator('.auth-card')).toBeVisible()
      await expectElementInsideViewport(page, '.auth-card')
      await expectNoHorizontalOverflow(page)
      await page.getByRole('button', { name: '关闭', exact: true }).click()
    })
  }
})

test.describe('移动端生成结果', () => {
  for (const viewport of viewports) {
    test(`${viewport.name}px：地图、路线控制与记账卡片`, async ({ page }) => {
      await preparePage(page)
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto('/')

      await page.getByRole('button', { name: '行程资料', exact: true }).click()
      await page.getByLabel('目的地').fill('成都')
      await page.getByRole('button', { name: '生成行程', exact: true }).click()

      await expect(page.locator('.result')).toBeVisible()
      await page.getByRole('button', { name: '关闭行程资料' }).click()
      await expect(page.locator('.info-panel')).toHaveCSS('opacity', '0')
      await expect(page.locator('.map')).toBeVisible()
      await expect(page.locator('.map')).toHaveAttribute('data-amap-ready', 'true')
      await expect(page.locator('.budget-summary')).toBeVisible()
      await expect(page.locator('.ledger-card.active')).toBeVisible()
      await expectNoHorizontalOverflow(page)
      await expectKeyTextFits(page)
      await expectElementInsideViewport(page, '.map-stage', false)
      await expectElementInsideViewport(page, '.budget-ledger', false)

      const speedButton = page.getByRole('button', { name: '4 倍', exact: true })
      await speedButton.click()
      await expect(speedButton).toHaveClass(/active/)
      await page.getByRole('button', { name: '播放路线', exact: true }).click()
      await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible()
    })
  }
})
