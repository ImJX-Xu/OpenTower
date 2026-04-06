'use client'

import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { Stars } from '@react-three/drei'
import * as THREE from 'three'

interface StarfieldProps {
    elevatorY: number
}

/**
 * Multi-layer starfield background:
 *  Layer 1 — drei Stars (static deep-space backdrop)
 *  Layer 2 — Custom flowing star particles (slow drift downward for "starlight rain" feel)
 */
export default function Starfield({ elevatorY }: StarfieldProps) {
    const flowRef = useRef<THREE.Points>(null)
    const groupRef = useRef<THREE.Group>(null)
    const timeRef = useRef(0)

    const FLOW_COUNT = 200

    const { positions, colors, sizes, speeds } = useMemo(() => {
        const pos = new Float32Array(FLOW_COUNT * 3)
        const col = new Float32Array(FLOW_COUNT * 3)
        const siz = new Float32Array(FLOW_COUNT)
        const spd = new Float32Array(FLOW_COUNT)

        for (let i = 0; i < FLOW_COUNT; i++) {
            // Spread across a large sphere around the scene
            pos[i * 3] = (Math.random() - 0.5) * 120      // x
            pos[i * 3 + 1] = (Math.random() - 0.5) * 100  // y
            pos[i * 3 + 2] = -10 - Math.random() * 60     // z (behind the scene)

            // Color: mix of white, pale blue, pale purple
            const colorChoice = Math.random()
            if (colorChoice < 0.5) {
                // White / warm white
                col[i * 3] = 0.95 + Math.random() * 0.05
                col[i * 3 + 1] = 0.92 + Math.random() * 0.08
                col[i * 3 + 2] = 0.98 + Math.random() * 0.02
            } else if (colorChoice < 0.8) {
                // Pale blue
                col[i * 3] = 0.6 + Math.random() * 0.2
                col[i * 3 + 1] = 0.75 + Math.random() * 0.2
                col[i * 3 + 2] = 1.0
            } else {
                // Pale purple / lavender
                col[i * 3] = 0.8 + Math.random() * 0.2
                col[i * 3 + 1] = 0.6 + Math.random() * 0.2
                col[i * 3 + 2] = 1.0
            }

            siz[i] = Math.random() * 0.35 + 0.08
            spd[i] = Math.random() * 0.3 + 0.1 // drift speed per star
        }

        return { positions: pos, colors: col, sizes: siz, speeds: spd }
    }, [])

    useFrame((_state, delta) => {
        timeRef.current += delta

        // Parallax — star group follows elevator slowly
        if (groupRef.current) {
            groupRef.current.position.y = elevatorY * 0.15
        }

        if (!flowRef.current) return
        const posAttr = flowRef.current.geometry.attributes.position as THREE.BufferAttribute
        const posArray = posAttr.array as Float32Array

        for (let i = 0; i < FLOW_COUNT; i++) {
            const speed = speeds[i]

            // Slow downward drift + gentle horizontal sway
            posArray[i * 3] += Math.sin(timeRef.current * 0.15 + i * 0.7) * 0.005
            posArray[i * 3 + 1] -= speed * delta * 0.8
            posArray[i * 3 + 2] += Math.cos(timeRef.current * 0.1 + i * 0.5) * 0.003

            // Wrap around: if star drifts too far down, reset to top
            if (posArray[i * 3 + 1] < -50) {
                posArray[i * 3 + 1] = 50 + Math.random() * 10
                posArray[i * 3] = (Math.random() - 0.5) * 120
            }
        }

        posAttr.needsUpdate = true
    })

    return (
        <group ref={groupRef}>
            {/* Layer 1: Static deep-space stars from drei */}
            <Stars
                radius={80}
                depth={60}
                count={5000}
                factor={6}
                saturation={0.15}
                fade
                speed={0.5}
            />

            {/* Layer 2: Flowing / drifting star particles */}
            <points ref={flowRef}>
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
                    size={0.25}
                    vertexColors
                    transparent
                    opacity={0.95}
                    sizeAttenuation
                    depthWrite={false}
                    blending={THREE.AdditiveBlending}
                />
            </points>
        </group>
    )
}
