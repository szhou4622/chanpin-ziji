import { describe, expect, it } from 'vitest'
import { layoutReportCloud } from './htmlReportCloudLayout'

describe('offline cloud packing', () => {
  it.each([[1000, 460], [400, 540]])('keeps all terms in bounds without collisions at %i × %i', (width, height) => {
    const items = Array.from({ length: 20 }, (_, i) => ({ keyword: i === 4 ? '比传统老坛或自制酸菜更值得选购' : `自然发酵${i}`, materialCount: i < 3 ? 3 : i < 8 ? 2 : 1 }))
    const boxes = layoutReportCloud(items, width, height)
    expect(boxes).toHaveLength(20)
    for (const [i, box] of boxes.entries()) {
      expect(box.x).toBeGreaterThanOrEqual(0)
      expect(box.y).toBeGreaterThanOrEqual(0)
      expect(box.x + box.width).toBeLessThanOrEqual(width)
      expect(box.y + box.height).toBeLessThanOrEqual(height)
      for (const other of boxes.slice(i + 1)) {
        expect(box.x < other.x + other.width && box.x + box.width > other.x && box.y < other.y + other.height && box.y + box.height > other.y).toBe(false)
      }
    }
    expect(boxes[0].font).toBeGreaterThan(boxes[19].font)
  })
})
