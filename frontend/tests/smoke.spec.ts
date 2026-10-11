import { test, expect, type Page } from '@playwright/test'

/**
 * Offline-safe bootstrap: the preview server only serves local assets, so
 * abort third-party requests (fonts, Unsplash, AMap) that would otherwise
 * delay the page load event on a slow or restricted network.
 */
async function prepareOfflinePage(page: Page) {
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url())
    if (url.hostname === 'localhost' || url.hostname === '127.0.0.1') {
      return route.continue()
    }
    return route.abort()
  })
}

test('主页核心控件可加载', async ({ page }) => {
  await prepareOfflinePage(page)
  await page.goto('/', { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('button', { name: '行程资料', exact: true })).toBeVisible()
  await expect(page.locator('header').getByRole('button', { name: 'AI 对话', exact: true })).toBeVisible()
  await expect(page.getByText('用户记忆', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '生成行程', exact: true })).toBeVisible()
})
