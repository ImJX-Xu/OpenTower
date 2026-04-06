'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

const TOTAL_FLOORS = 50
const FLOOR_HEIGHT = 4.0
const LERP_SPEED = 0.06

export interface ElevatorState {
    currentFloor: number
    elevatorY: number
    isMoving: boolean
    goToFloor: (floor: number) => void
    totalFloors: number
}

export function useElevator(): ElevatorState {
    const [currentFloor, setCurrentFloor] = useState(1)
    const targetFloorRef = useRef(1)
    const elevatorYRef = useRef(0)
    const [elevatorY, setElevatorY] = useState(0)
    const [isMoving, setIsMoving] = useState(false)
    const animFrameRef = useRef<number>(0)
    const lastTouchYRef = useRef<number>(0)
    const scrollAccumRef = useRef(0)

    const goToFloor = useCallback((floor: number) => {
        const clamped = Math.max(1, Math.min(TOTAL_FLOORS, floor))
        targetFloorRef.current = clamped
        setIsMoving(true)
    }, [])

    // Wheel handler
    useEffect(() => {
        const handleWheel = (e: WheelEvent) => {
            e.preventDefault()
            scrollAccumRef.current += e.deltaY

            if (Math.abs(scrollAccumRef.current) > 80) {
                const direction = scrollAccumRef.current > 0 ? 1 : -1
                const nextFloor = Math.max(1, Math.min(TOTAL_FLOORS, targetFloorRef.current + direction))
                targetFloorRef.current = nextFloor
                setIsMoving(true)
                scrollAccumRef.current = 0
            }
        }

        window.addEventListener('wheel', handleWheel, { passive: false })
        return () => window.removeEventListener('wheel', handleWheel)
    }, [])

    // Touch handler
    useEffect(() => {
        const handleTouchStart = (e: TouchEvent) => {
            lastTouchYRef.current = e.touches[0].clientY
        }

        const handleTouchMove = (e: TouchEvent) => {
            e.preventDefault()
            const deltaY = lastTouchYRef.current - e.touches[0].clientY
            lastTouchYRef.current = e.touches[0].clientY

            scrollAccumRef.current += deltaY

            if (Math.abs(scrollAccumRef.current) > 40) {
                const direction = scrollAccumRef.current > 0 ? 1 : -1
                const nextFloor = Math.max(1, Math.min(TOTAL_FLOORS, targetFloorRef.current + direction))
                targetFloorRef.current = nextFloor
                setIsMoving(true)
                scrollAccumRef.current = 0
            }
        }

        window.addEventListener('touchstart', handleTouchStart, { passive: false })
        window.addEventListener('touchmove', handleTouchMove, { passive: false })
        return () => {
            window.removeEventListener('touchstart', handleTouchStart)
            window.removeEventListener('touchmove', handleTouchMove)
        }
    }, [])

    // Keyboard handler
    useEffect(() => {
        const handleKey = (e: KeyboardEvent) => {
            if (e.key === 'ArrowUp' || e.key === 'w') {
                goToFloor(targetFloorRef.current + 1)
            } else if (e.key === 'ArrowDown' || e.key === 's') {
                goToFloor(targetFloorRef.current - 1)
            }
        }

        window.addEventListener('keydown', handleKey)
        return () => window.removeEventListener('keydown', handleKey)
    }, [goToFloor])

    // Animation loop — smooth lerp
    useEffect(() => {
        const animate = () => {
            const targetY = (targetFloorRef.current - 1) * FLOOR_HEIGHT
            const currentY = elevatorYRef.current
            const diff = targetY - currentY

            if (Math.abs(diff) > 0.01) {
                elevatorYRef.current += diff * LERP_SPEED
                setElevatorY(elevatorYRef.current)
                setIsMoving(true)

                const approxFloor = Math.round(elevatorYRef.current / FLOOR_HEIGHT) + 1
                setCurrentFloor(Math.max(1, Math.min(TOTAL_FLOORS, approxFloor)))
            } else {
                elevatorYRef.current = targetY
                setElevatorY(targetY)
                setIsMoving(false)
                setCurrentFloor(targetFloorRef.current)
            }

            animFrameRef.current = requestAnimationFrame(animate)
        }

        animFrameRef.current = requestAnimationFrame(animate)
        return () => cancelAnimationFrame(animFrameRef.current)
    }, [])

    return {
        currentFloor,
        elevatorY,
        isMoving,
        goToFloor,
        totalFloors: TOTAL_FLOORS,
    }
}
