import { test, expect } from '@playwright/test'

test('主页核心控件可加载', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('button', { name: '行程资料', exact: true })).toBeVisible()
  await expect(page.locator('header').getByRole('button', { name: 'AI 对话', exact: true })).toBeVisible()
  await expect(page.getByText('用户记忆', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '生成行程', exact: true })).toBeVisible()
})