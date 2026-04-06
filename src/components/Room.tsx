'use client'

import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import Character from './Character'
import { getWallpaperTexture } from '../utils/wallpapers'

interface RoomProps {
    position: [number, number, number]
    roomIndex: number
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

const POSES: Array<'typing' | 'standing' | 'phone' | 'sitting' | 'leaning'> = [
    'typing', 'standing', 'phone', 'sitting', 'leaning'
]

const MONITOR_COLORS = ['#0044ff', '#00ff88', '#ff4400', '#ff00ff', '#ffaa00', '#00f5ff']

export default function Room({ position, roomIndex, floorIndex, floorActive }: RoomProps) {
    const monitorRef = useRef<THREE.Mesh>(null)
    const seed = floorIndex * 100 + roomIndex
    const rng = useMemo(() => seededRandom(seed), [seed])

    const wallpaperIndex = useMemo(() => Math.floor(rng() * 10), [rng])
    const wallTexture = useMemo(() => {
        if (typeof document === 'undefined') return null
        return getWallpaperTexture(wallpaperIndex, seed)
    }, [wallpaperIndex, seed])

    const numCharacters = 1
    const monitorColor = useMemo(() => MONITOR_COLORS[Math.floor(rng() * MONITOR_COLORS.length)], [rng])
    const hasPlant = useMemo(() => rng() > 0.4, [rng])

    // Monitor screen flicker
    useFrame((state) => {
        if (!floorActive || !monitorRef.current) return
        const mat = monitorRef.current.material as THREE.MeshStandardMaterial
        mat.emissiveIntensity = 1.5 + Math.sin(state.clock.elapsedTime * 3 + seed) * 0.4
    })

    const roomW = 3.2
    const roomD = 2.8
    const roomH = 3.5
    const wallThickness = 0.06

    return (
        <group position={position}>
            {/* Back Wall */}
            <mesh position={[0, roomH / 2, -roomD / 2]}>
                <boxGeometry args={[roomW, roomH, wallThickness]} />
                {wallTexture ? (
                    <meshStandardMaterial map={wallTexture} roughness={0.8} />
                ) : (
                    <meshStandardMaterial color="#1a1a2a" roughness={0.8} />
                )}
            </mesh>

            {/* Left Wall */}
            <mesh position={[-roomW / 2, roomH / 2, 0]}>
                <boxGeometry args={[wallThickness, roomH, roomD]} />
                <meshStandardMaterial color="#151520" roughness={0.9} />
            </mesh>

            {/* Right Wall */}
            <mesh position={[roomW / 2, roomH / 2, 0]}>
                <boxGeometry args={[wallThickness, roomH, roomD]} />
                <meshStandardMaterial color="#151520" roughness={0.9} />
            </mesh>

            {/* Ceiling Light Strip */}
            <mesh position={[0, roomH - 0.05, 0]}>
                <boxGeometry args={[roomW * 0.6, 0.04, 0.15]} />
                <meshStandardMaterial
                    color="#ffffff"
                    emissive="#ccddff"
                    emissiveIntensity={1.2}
                />
            </mesh>

            {/* Desk */}
            <group position={[0, 0, -0.5]}>
                {/* Desk top */}
                <mesh position={[0, 0.72, 0]}>
                    <boxGeometry args={[1.4, 0.05, 0.7]} />
                    <meshStandardMaterial color="#2a2a35" roughness={0.6} metalness={0.3} />
                </mesh>
                {/* Desk legs */}
                {[[-0.6, 0.36, -0.28], [0.6, 0.36, -0.28], [-0.6, 0.36, 0.28], [0.6, 0.36, 0.28]].map((pos, i) => (
                    <mesh key={i} position={pos as [number, number, number]}>
                        <boxGeometry args={[0.04, 0.72, 0.04]} />
                        <meshStandardMaterial color="#1a1a22" metalness={0.5} />
                    </mesh>
                ))}

                {/* Monitor */}
                <group position={[0, 1.05, -0.15]}>
                    {/* Screen */}
                    <mesh ref={monitorRef}>
                        <boxGeometry args={[0.6, 0.38, 0.02]} />
                        <meshStandardMaterial
                            color="#000000"
                            emissive={monitorColor}
                            emissiveIntensity={1.5}
                        />
                    </mesh>
                    {/* Monitor stand */}
                    <mesh position={[0, -0.22, 0.03]}>
                        <boxGeometry args={[0.06, 0.1, 0.06]} />
                        <meshStandardMaterial color="#222222" metalness={0.7} />
                    </mesh>
                    {/* Monitor base */}
                    <mesh position={[0, -0.28, 0.05]}>
                        <boxGeometry args={[0.2, 0.02, 0.12]} />
                        <meshStandardMaterial color="#222222" metalness={0.7} />
                    </mesh>
                </group>

                {/* Keyboard */}
                <mesh position={[0, 0.76, 0.15]}>
                    <boxGeometry args={[0.35, 0.015, 0.12]} />
                    <meshStandardMaterial color="#111111" roughness={0.7} />
                </mesh>

                {/* Coffee mug */}
                <mesh position={[0.55, 0.8, 0.1]}>
                    <cylinderGeometry args={[0.035, 0.03, 0.08, 8]} />
                    <meshStandardMaterial color="#ffffff" roughness={0.6} />
                </mesh>
            </group>

            {/* Chair */}
            <group position={[0, 0, 0.4]}>
                {/* Seat */}
                <mesh position={[0, 0.42, 0]}>
                    <boxGeometry args={[0.4, 0.05, 0.4]} />
                    <meshStandardMaterial color="#1a1a2a" />
                </mesh>
                {/* Back */}
                <mesh position={[0, 0.7, -0.18]}>
                    <boxGeometry args={[0.38, 0.5, 0.04]} />
                    <meshStandardMaterial color="#1a1a2a" />
                </mesh>
                {/* Base */}
                <mesh position={[0, 0.2, 0]}>
                    <cylinderGeometry args={[0.03, 0.03, 0.4, 6]} />
                    <meshStandardMaterial color="#333333" metalness={0.8} />
                </mesh>
                {/* Wheel base */}
                <mesh position={[0, 0.02, 0]} rotation={[0, 0, 0]}>
                    <cylinderGeometry args={[0.18, 0.18, 0.02, 5]} />
                    <meshStandardMaterial color="#222222" metalness={0.7} />
                </mesh>
            </group>

            {/* Plant */}
            {hasPlant && (
                <group position={[roomW / 2 - 0.3, 0, roomD / 2 - 0.3]}>
                    {/* Pot */}
                    <mesh position={[0, 0.15, 0]}>
                        <cylinderGeometry args={[0.12, 0.1, 0.3, 8]} />
                        <meshStandardMaterial color="#443322" roughness={0.9} />
                    </mesh>
                    {/* Plant foliage */}
                    <mesh position={[0, 0.45, 0]}>
                        <sphereGeometry args={[0.18, 6, 6]} />
                        <meshStandardMaterial color="#115522" roughness={0.8} />
                    </mesh>
                    <mesh position={[0.08, 0.55, 0.05]}>
                        <sphereGeometry args={[0.12, 6, 6]} />
                        <meshStandardMaterial color="#118833" roughness={0.8} />
                    </mesh>
                </group>
            )}

            {/* Characters (NPCs) */}
            {Array.from({ length: numCharacters }, (_, i) => {
                const charSeed = seed * 10 + i
                const rngC = seededRandom(charSeed)
                const poseIndex = Math.floor(rngC() * POSES.length)
                const xPos = (i - (numCharacters - 1) / 2) * 0.8
                const zPos = i === 0 ? 0.3 : rngC() * 0.6 - 0.3

                return (
                    <Character
                        key={i}
                        position={[xPos, 0, zPos]}
                        pose={POSES[poseIndex]}
                        seed={charSeed}
                        floorActive={floorActive}
                    />
                )
            })}
        </group>
    )
}
