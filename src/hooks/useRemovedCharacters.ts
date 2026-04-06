import { useSyncExternalStore, useCallback } from 'react'

// Module-level store for removed characters (by seed)
let removedSeeds = new Set<number>()
const listeners = new Set<() => void>()

function subscribe(listener: () => void) {
    listeners.add(listener)
    return () => listeners.delete(listener)
}

function getSnapshot() {
    return removedSeeds
}

function removeCharacter(seed: number) {
    removedSeeds = new Set(removedSeeds)
    removedSeeds.add(seed)
    listeners.forEach((l) => l())
}

export function useRemovedCharacters() {
    const removed = useSyncExternalStore(subscribe, getSnapshot)

    const remove = useCallback((seed: number) => {
        removeCharacter(seed)
    }, [])

    const isRemoved = useCallback(
        (seed: number) => removed.has(seed),
        [removed],
    )

    return { isRemoved, remove }
}
