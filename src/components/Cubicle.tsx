'use client'

import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import Character from './Character'

interface CubicleProps {
    position: [number, number, number]
    col: number
    row: number
    floorIndex: number
    floorActive: boolean
}

function seededRandom(seed: number) {
    let s = seed
    return () => {
        s = (s * 9301 + 49297) % 233280
        return s / 233280
    }
}

const MONITOR_COLORS = ['#0044ff', '#00ff88', '#ff4400', '#ff00ff', '#ffaa00', '#00f5ff', '#4488ff', '#ff6644']

export default function Cubicle({ position, col, row, floorIndex, floorActive }: CubicleProps) {
    const monitorRef = useRef<THREE.Mesh>(null)
    const ledRef = useRef<THREE.Mesh>(null)
    const scanLineRef = useRef(0)
    const seed = floorIndex * 1000 + row * 100 + col
    const rng = useMemo(() => seededRandom(seed), [seed])

    const monitorColor = useMemo(() => MONITOR_COLORS[Math.floor(rng() * MONITOR_COLORS.length)], [rng])
    const isOverloaded = useMemo(() => rng() < 0.1, [rng])  // 10% overloaded
    const monitorSize = useMemo(() => 0.35 + rng() * 0.15, [rng])
    const ledPhase = useMemo(() => rng() * Math.PI * 2, [rng])

    // Monitor scan line + LED pulse animation
    useFrame((state) => {
        if (!floorActive) return
        const t = state.clock.elapsedTime

        if (monitorRef.current) {
            const mat = monitorRef.current.material as THREE.MeshStandardMaterial
            // Scan line effect via intensity modulation
            scanLineRef.current = (scanLineRef.current + 0.03) % 1
            const scanPulse = 1.0 + Math.sin(t * 2 + seed) * 0.3

            if (isOverloaded) {
                // Overloaded: rapid red flicker
                mat.emissive.set(Math.random() > 0.15 ? '#ff1100' : '#330000')
                mat.emissiveIntensity = 1.5 + Math.random() * 2
            } else {
                mat.emissiveIntensity = scanPulse
            }
        }

        // LED strip pulse
        if (ledRef.current) {
            const mat = ledRef.current.material as THREE.MeshStandardMaterial
            mat.emissiveIntensity = 0.8 + Math.sin(t * 1.5 + ledPhase) * 0.5
        }
    })

    return (
        <group position={position}>
            {/* === Server Rack Pod Frame === */}
            {/* Left rail */}
            <mesh position={[-0.85, 0.5, 0]}>
                <boxGeometry args={[0.04, 1.0, 0.04]} />
                <meshStandardMaterial color="#0a0a12" metalness={0.95} roughness={0.2} transparent opacity={0.5} />
            </mesh>
            {/* Right rail */}
            <mesh position={[0.85, 0.5, 0]}>
                <boxGeometry args={[0.04, 1.0, 0.04]} />
                <meshStandardMaterial color="#0a0a12" metalness={0.95} roughness={0.2} transparent opacity={0.5} />
            </mesh>
            {/* Top crossbar */}
            <mesh position={[0, 1.0, 0]}>
                <boxGeometry args={[1.74, 0.03, 0.04]} />
                <meshStandardMaterial color="#0a0a12" metalness={0.95} roughness={0.2} transparent opacity={0.5} />
            </mesh>
            {/* Base plate */}
            <mesh position={[0, 0.02, 0]}>
                <boxGeometry args={[1.74, 0.04, 1.2]} />
                <meshStandardMaterial color="#080810" metalness={0.8} roughness={0.3} />
            </mesh>

            {/* Vertical LED strip — activity indicator */}
            <mesh ref={ledRef} position={[-0.88, 0.5, 0]}>
                <boxGeometry args={[0.02, 0.8, 0.02]} />
                <meshStandardMaterial
                    color="#000"
                    emissive={isOverloaded ? '#ff1100' : monitorColor}
                    emissiveIntensity={1.0}
                />
            </mesh>

            {/* Data viewport (monitor) — in front of rack */}
            <mesh ref={monitorRef} position={[0, 0.75, 0.15]}>
                <boxGeometry args={[monitorSize * 2.4, monitorSize * 1.5, 0.015]} />
                <meshStandardMaterial
                    color="#000000"
                    emissive={isOverloaded ? '#ff1100' : monitorColor}
                    emissiveIntensity={1.2}
                />
            </mesh>
            {/* Monitor frame */}
            <mesh position={[0, 0.75, 0.14]}>
                <boxGeometry args={[monitorSize * 2.4 + 0.03, monitorSize * 1.5 + 0.03, 0.01]} />
                <meshStandardMaterial color="#0a0a10" metalness={0.9} roughness={0.2} />
            </mesh>

            {/* Cable conduits at base */}
            <mesh position={[0.3, 0.01, 0.2]}>
                <cylinderGeometry args={[0.015, 0.015, 0.6, 4]} />
                <meshStandardMaterial color="#0e0e14" metalness={0.7} />
            </mesh>
            <mesh position={[-0.3, 0.01, 0.2]} rotation={[0, 0.5, 0]}>
                <cylinderGeometry args={[0.015, 0.015, 0.5, 4]} />
                <meshStandardMaterial color="#0e0e14" metalness={0.7} />
            </mesh>

            {/* Neural node — only in front row for performance */}
            {row === 2 && (
                <Character
                    position={[0, 0, 0.25]}
                    pose="typing"
                    seed={seed}
                    floorActive={floorActive}
                />
            )}
        </group>
    )
}
