'use client'

import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

interface HoloParticlesProps {
    count?: number
    elevatorY: number
}

export default function HoloParticles({ count = 40, elevatorY }: HoloParticlesProps) {
    const pointsRef = useRef<THREE.Points>(null)
    const timeRef = useRef(0)

    const { positions, colors, sizes } = useMemo(() => {
        const pos = new Float32Array(count * 3)
        const col = new Float32Array(count * 3)
        const siz = new Float32Array(count)

        for (let i = 0; i < count; i++) {
            pos[i * 3] = (Math.random() - 0.5) * 30
            pos[i * 3 + 1] = Math.random() * 100
            pos[i * 3 + 2] = (Math.random() - 0.5) * 15

            // Cyan / magenta / white color mix
            const colorChoice = Math.random()
            if (colorChoice < 0.4) {
                // Cyan
                col[i * 3] = 0
                col[i * 3 + 1] = 0.9 + Math.random() * 0.1
                col[i * 3 + 2] = 1
            } else if (colorChoice < 0.7) {
                // Magenta
                col[i * 3] = 1
                col[i * 3 + 1] = 0
                col[i * 3 + 2] = 1
            } else {
                // White
                col[i * 3] = 1
                col[i * 3 + 1] = 1
                col[i * 3 + 2] = 1
            }

            siz[i] = Math.random() * 3 + 0.5
        }

        return { positions: pos, colors: col, sizes: siz }
    }, [count])

    useFrame((state, delta) => {
        if (!pointsRef.current) return
        timeRef.current += delta

        const posAttr = pointsRef.current.geometry.attributes.position as THREE.BufferAttribute
        const posArray = posAttr.array as Float32Array

        for (let i = 0; i < count; i++) {
            // Slow drift
            posArray[i * 3] += Math.sin(timeRef.current * 0.2 + i * 0.1) * 0.003
            posArray[i * 3 + 1] += Math.sin(timeRef.current * 0.15 + i * 0.3) * 0.005
            posArray[i * 3 + 2] += Math.cos(timeRef.current * 0.18 + i * 0.2) * 0.003
        }

        posAttr.needsUpdate = true

        // Follow elevator closely
        pointsRef.current.position.y = elevatorY * 0.9
    })

    return (
        <points ref={pointsRef}>
            <bufferGeometry>
                <bufferAttribute
                    attach="attributes-position"
                    args={[positions, 3]}
                />
                <bufferAttribute
                    attach="attributes-color"
                    args={[colors, 3]}
                />
            </bufferGeometry>
            <pointsMaterial
                size={0.06}
                vertexColors
                transparent
                opacity={0.6}
                sizeAttenuation
                depthWrite={false}
                blending={THREE.AdditiveBlending}
            />
        </points>
    )
}
