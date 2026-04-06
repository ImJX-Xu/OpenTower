'use client'

import { useMemo, useRef, useEffect, useState } from 'react'
import { ElevatorState } from '../../hooks/useElevator'
import { getFloorShortName, buildingName, buildingSubtitle } from '../../utils/floorConfig'

interface HUDProps {
    elevator: ElevatorState
}

// Animated counter that cycles rapidly
function useAnimatedCounter(target: number, speed: number = 0.1) {
    const [value, setValue] = useState(target)
    const rafRef = useRef<number>(0)

    useEffect(() => {
        let current = value
        const animate = () => {
            current += (target - current) * speed + (Math.random() - 0.5) * 0.3
            setValue(parseFloat(current.toFixed(1)))
            rafRef.current = requestAnimationFrame(animate)
        }
        rafRef.current = requestAnimationFrame(animate)
        return () => cancelAnimationFrame(rafRef.current)
    }, [target, speed])

    return value
}

export default function HUD({ elevator }: HUDProps) {
    const { currentFloor, goToFloor, totalFloors } = elevator
    const navRef = useRef<HTMLDivElement>(null)
    const [hoveredFloor, setHoveredFloor] = useState<number | null>(null)

    // Simulated live metrics
    const [metrics, setMetrics] = useState({
        tokenBurn: 45.2,
        zicr: 99.2,
        roi: 45.20,
        activeNodes: 1147,
    })

    // Update metrics every 100ms for live feel
    useEffect(() => {
        const interval = setInterval(() => {
            setMetrics(prev => ({
                tokenBurn: Math.max(20, prev.tokenBurn + (Math.random() - 0.48) * 3),
                zicr: Math.min(99.9, Math.max(97, prev.zicr + (Math.random() - 0.5) * 0.3)),
                roi: prev.roi + Math.random() * 0.15,
                activeNodes: Math.min(1200, Math.max(1100, prev.activeNodes + Math.floor((Math.random() - 0.45) * 5))),
            }))
        }, 100)
        return () => clearInterval(interval)
    }, [])

    // Auto-scroll floor nav
    useEffect(() => {
        if (!navRef.current) return
        const container = navRef.current
        const activeBtn = container.querySelector('.floor-btn.active') as HTMLElement
        if (activeBtn) {
            const containerRect = container.getBoundingClientRect()
            const btnRect = activeBtn.getBoundingClientRect()
            const offset = btnRect.top - containerRect.top - containerRect.height / 2 + btnRect.height / 2
            container.scrollTop += offset * 0.3
        }
    }, [currentFloor])

    const visibleFloors = useMemo(() => {
        const floors: number[] = []
        for (let i = totalFloors; i >= 1; i--) {
            if (
                i === totalFloors ||
                i === 1 ||
                i <= 20 ||
                i % 5 === 0 ||
                i === currentFloor ||
                Math.abs(i - currentFloor) <= 2
            ) {
                floors.push(i)
            }
        }
        return [...new Set(floors)].sort((a, b) => b - a)
    }, [totalFloors, currentFloor])

    const floorName = getFloorShortName(currentFloor)

    return (
        <div className="hud">
            {/* Title */}
            <div className="title-overlay">{buildingName} — {buildingSubtitle}</div>

            {/* Floor Info Panel */}
            <div className="floor-info">
                <span className="floor-label">SECTOR</span>
                <span className="floor-number">{currentFloor.toString().padStart(2, '0')}</span>
                <span className="floor-dept">{floorName}</span>

                {/* Power Metrics */}
                <div className="metrics-panel">
                    <div className="metric">
                        <span className="metric-label">TOKEN BURN</span>
                        <span className="metric-value burn">{metrics.tokenBurn.toFixed(1)}k/s</span>
                    </div>
                    <div className="metric">
                        <span className="metric-label">ZICR</span>
                        <span className="metric-value zicr">{metrics.zicr.toFixed(1)}%</span>
                    </div>
                    <div className="metric">
                        <span className="metric-label">ROI</span>
                        <span className="metric-value roi">+${metrics.roi.toFixed(2)}</span>
                    </div>
                    <div className="metric">
                        <span className="metric-label">NODES</span>
                        <span className="metric-value nodes">{metrics.activeNodes}/1200</span>
                    </div>
                </div>
            </div>

            {/* Floor Navigation */}
            <div className="floor-nav" ref={navRef}>
                <div className="floor-nav-track">
                    {visibleFloors.map((floor) => {
                        const isActive = floor === currentFloor
                        const isNear = Math.abs(floor - currentFloor) <= 1
                        const isLandmark = floor === totalFloors || floor === 1 || floor % 10 === 0

                        return (
                            <button
                                key={floor}
                                className={`floor-btn ${isActive ? 'active' : ''} ${isNear ? 'near' : ''} ${isLandmark ? 'landmark' : ''}`}
                                onClick={() => goToFloor(floor)}
                                onMouseEnter={() => setHoveredFloor(floor)}
                                onMouseLeave={() => setHoveredFloor(null)}
                                title={`F${floor} — ${getFloorShortName(floor)}`}
                            >
                                <span className="floor-btn-num">{floor}</span>
                                {(hoveredFloor === floor || isActive) && (
                                    <span className="floor-btn-label">{getFloorShortName(floor)}</span>
                                )}
                            </button>
                        )
                    })}
                </div>
            </div>

            {/* Scroll Hint */}
            <div className="scroll-hint">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 5v14M5 12l7 7 7-7" />
                </svg>
                SCROLL · {totalFloors} SECTORS
            </div>
        </div>
    )
}
