'use client'

import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

interface CityBackgroundProps {
    elevatorY: number
}

function seededRandom(seed: number) {
    let s = seed
    return () => {
        s = (s * 9301 + 49297) % 233280
        return s / 233280
    }
}

interface CityBuilding {
    x: number
    z: number
    width: number
    depth: number
    height: number
    color: string
    emissive: string
    emissiveIntensity: number
}

export default function CityBackground({ elevatorY }: CityBackgroundProps) {
    const groupRef = useRef<THREE.Group>(null)
    const neonSignsRef = useRef<THREE.Group>(null)

    const buildings = useMemo<CityBuilding[]>(() => {
        const rng = seededRandom(42)
        const result: CityBuilding[] = []
        const colors = ['#0a0a15', '#0c0c18', '#080812', '#0e0e1a', '#0a0a20']
        const emissives = ['#000822', '#001133', '#110022', '#002211', '#111100']

        for (let i = 0; i < 60; i++) {
            const x = (rng() - 0.5) * 120
            const z = -15 - rng() * 40
            const width = rng() * 3 + 1
            const depth = rng() * 3 + 1
            const height = rng() * 30 + 5
            result.push({
                x,
                z,
                width,
                depth,
                height,
                color: colors[Math.floor(rng() * colors.length)],
                emissive: emissives[Math.floor(rng() * emissives.length)],
                emissiveIntensity: rng() * 0.5 + 0.1,
            })
        }
        return result
    }, [])

    const neonSigns = useMemo(() => {
        const rng = seededRandom(99)
        const signs: Array<{
            position: [number, number, number]
            scale: [number, number, number]
            color: string
        }> = []
        const signColors = ['#ff00ff', '#00f5ff', '#ffaa00', '#ff4444', '#00ff88']

        for (let i = 0; i < 15; i++) {
            signs.push({
                position: [
                    (rng() - 0.5) * 80,
                    rng() * 25 + 5,
                    -12 - rng() * 30,
                ],
                scale: [rng() * 3 + 1, rng() * 0.8 + 0.2, 0.05],
                color: signColors[Math.floor(rng() * signColors.length)],
            })
        }
        return signs
    }, [])

    // Parallax effect — background moves slower
    useFrame(() => {
        if (groupRef.current) {
            groupRef.current.position.y = elevatorY * 0.3
        }
        if (neonSignsRef.current) {
            neonSignsRef.current.position.y = elevatorY * 0.15
        }
    })

    return (
        <>
            {/* City buildings */}
            <group ref={groupRef}>
                {buildings.map((b, i) => (
                    <mesh key={i} position={[b.x, b.height / 2, b.z]}>
                        <boxGeometry args={[b.width, b.height, b.depth]} />
                        <meshStandardMaterial
                            color={b.color}
                            emissive={b.emissive}
                            emissiveIntensity={b.emissiveIntensity}
                            roughness={0.8}
                        />
                    </mesh>
                ))}

                {/* Window lights on buildings */}
                {buildings.slice(0, 20).map((b, i) => {
                    const windowCount = Math.floor(b.height / 2)
                    return Array.from({ length: Math.min(windowCount, 8) }, (_, j) => (
                        <mesh
                            key={`w-${i}-${j}`}
                            position={[
                                b.x + (j % 2 === 0 ? 0.3 : -0.3),
                                j * 2 + 2,
                                b.z + b.depth / 2 + 0.01,
                            ]}
                        >
                            <planeGeometry args={[0.3, 0.5]} />
                            <meshStandardMaterial
                                color="#000"
                                emissive={j % 3 === 0 ? '#ffaa44' : '#4488ff'}
                                emissiveIntensity={0.6}
                            />
                        </mesh>
                    ))
                })}
            </group>

            {/* Neon signs */}
            <group ref={neonSignsRef}>
                {neonSigns.map((sign, i) => (
                    <mesh key={i} position={sign.position}>
                        <boxGeometry args={sign.scale} />
                        <meshStandardMaterial
                            color="#000"
                            emissive={sign.color}
                            emissiveIntensity={1.5}
                        />
                    </mesh>
                ))}
            </group>
        </>
    )
}
