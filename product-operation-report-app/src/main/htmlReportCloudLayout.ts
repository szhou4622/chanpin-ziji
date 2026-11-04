export interface CloudBox { x: number; y: number; width: number; height: number; font: number }

/** Deterministic centre-out packing: frequency controls type size, rectangles never overlap.
 * Coordinates are exported as percentages, so the offline report needs no layout script. */
export function layoutReportCloud(items: Array<{ keyword: string; materialCount: number }>, width = 1000, height = 460): CloudBox[] {
  const min = Math.min(...items.map(item => item.materialCount))
  const max = Math.max(...items.map(item => item.materialCount))
  const mobile = width < 500
  const boxes: CloudBox[] = []
  const result: CloudBox[] = []
  const ordered = items.map((item, index) => ({ ...item, index })).sort((a, b) => b.materialCount - a.materialCount || a.index - b.index)
  for (const item of ordered) {
    const units = [...item.keyword].reduce((sum, char) => sum + (/[^\x00-\xff]/u.test(char) ? 1.05 : .67), 0)
    const ratio = max === min ? .45 : (item.materialCount - min) / (max - min)
    let font = (mobile ? 16 : 24) + ratio * (mobile ? 22 : 46)
    font = Math.min(font, (width - 36) / Math.max(1, units))
    let found: CloudBox | undefined
    for (let attempt = 0; attempt < 20 && !found; attempt++) {
      const w = units * font + 12, h = font * 1.5 + 8
      for (let step = 0; step < 9000; step++) {
        const angle = step * .19, radius = .15 * step
        const x = width / 2 + Math.cos(angle) * radius * 1.6 - w / 2
        const y = height / 2 + Math.sin(angle) * radius - h / 2
        if (x < 8 || y < 8 || x + w > width - 8 || y + h > height - 8) continue
        if (boxes.some(box => x < box.x + box.width + 5 && x + w + 5 > box.x && y < box.y + box.height + 5 && y + h + 5 > box.y)) continue
        found = { x, y, width: w, height: h, font }
        break
      }
      if (!found) font *= .9
    }
    if (!found) throw new Error('Word cloud exceeds available layout area')
    boxes.push(found)
    result[item.index] = found
  }
  return result
}

export function reportCloudPosition(box: CloudBox, width: number, height: number, prefix: string): string {
  return `--${prefix}-x:${(box.x / width * 100).toFixed(3)}%;--${prefix}-y:${(box.y / height * 100).toFixed(3)}%;--${prefix}-w:${(box.width / width * 100).toFixed(3)}%;--${prefix}-h:${(box.height / height * 100).toFixed(3)}%;--${prefix}-font:${(box.font / width * 100).toFixed(3)}cqw`
}
