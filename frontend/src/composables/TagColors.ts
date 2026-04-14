export const TAG_COLOR_PRESETS = [
  '#3B82F6',
  '#14B8A6',
  '#10B981',
  '#84CC16',
  '#F59E0B',
  '#F97316',
  '#EF4444',
  '#EC4899',
  '#8B5CF6',
  '#6366F1',
  '#06B6D4',
  '#64748B',
]

const SOFT_SATURATION_STEPS = [0.58, 0.62, 0.56]
const SOFT_LIGHTNESS_STEPS = [0.48, 0.52, 0.5]
const AVOID_HUE_RANGES: Array<[number, number]> = [
  [0.11, 0.18],
]

function normalizeColor(color?: string) {
  return (color || '').trim().toUpperCase()
}

function hslToHex(hue: number, saturation = 0.72, lightness = 0.56) {
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation
  const huePrime = hue * 6
  const x = chroma * (1 - Math.abs((huePrime % 2) - 1))

  let red = 0
  let green = 0
  let blue = 0

  if (huePrime >= 0 && huePrime < 1) [red, green, blue] = [chroma, x, 0]
  else if (huePrime < 2) [red, green, blue] = [x, chroma, 0]
  else if (huePrime < 3) [red, green, blue] = [0, chroma, x]
  else if (huePrime < 4) [red, green, blue] = [0, x, chroma]
  else if (huePrime < 5) [red, green, blue] = [x, 0, chroma]
  else [red, green, blue] = [chroma, 0, x]

  const match = lightness - chroma / 2
  const toHex = (value: number) =>
    Math.round((value + match) * 255)
      .toString(16)
      .padStart(2, '0')
      .toUpperCase()

  return `#${toHex(red)}${toHex(green)}${toHex(blue)}`
}

function isAvoidedHue(hue: number) {
  return AVOID_HUE_RANGES.some(([start, end]) => hue >= start && hue <= end)
}

function generateExtendedColor(existingColors: Set<string>) {
  let attempts = existingColors.size
  while (true) {
    const hue = ((attempts * 137.508) % 360) / 360
    if (isAvoidedHue(hue)) {
      attempts += 1
      continue
    }
    const saturation = SOFT_SATURATION_STEPS[attempts % SOFT_SATURATION_STEPS.length]
    const lightness = SOFT_LIGHTNESS_STEPS[attempts % SOFT_LIGHTNESS_STEPS.length]
    const color = hslToHex(hue, saturation, lightness)
    if (!existingColors.has(color)) return color
    attempts += 1
  }
}

export function getDistinctTagColor(existingColors: string[] = [], preferRandom = true) {
  const normalizedExisting = new Set(existingColors.map(normalizeColor))
  const availablePresets = TAG_COLOR_PRESETS.filter(color => !normalizedExisting.has(normalizeColor(color)))
  if (availablePresets.length) {
    if (preferRandom) {
      return availablePresets[Math.floor(Math.random() * availablePresets.length)]
    }
    return availablePresets[0]
  }
  return generateExtendedColor(normalizedExisting)
}

export function getRandomTagColor(existingColors: string[] = []) {
  return getDistinctTagColor(existingColors, true)
}
