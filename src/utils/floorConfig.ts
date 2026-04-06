import floorsData from '../data/floors.json'

export interface FloorConfig {
    name: string
    short: string
    description: string
}

/**
 * Look up a floor's label config from floors.json.
 * Falls back to a generic label if no range matches.
 */
export function getFloorConfig(floor: number): FloorConfig {
    for (const entry of floorsData.floors) {
        const [lo, hi] = entry.range
        if (floor >= lo && floor <= hi) {
            return {
                name: entry.name,
                short: entry.short,
                description: entry.description,
            }
        }
    }
    return { name: 'UNKNOWN_SECTOR', short: 'UNKNOWN', description: '' }
}

/** Full floor name (used in 3D scene labels) */
export function getFloorName(floor: number): string {
    return getFloorConfig(floor).name
}

/** Short floor name (used in HUD) */
export function getFloorShortName(floor: number): string {
    return getFloorConfig(floor).short
}

/** Building metadata */
export const buildingName = floorsData.buildingName
export const buildingSubtitle = floorsData.subtitle
export const rooftopConfig = floorsData.rooftop
