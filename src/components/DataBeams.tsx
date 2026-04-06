'use client'

import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

interface DataBeamsProps {
    elevatorY: number
    totalFloors: number
}

interface Beam {
    x: number
    speed: number
    color: string
    width: number
    phase: number
    height: number
}

const BEAM_COLORS = ['#00f5ff', '#ff00ff', '#00ff88', '#ffaa00', '#4488ff']

export default function DataBeams({ elevatorY, totalFloors }: DataBeamsProps) {
    const groupRef = useRef<THREE.Group>(null)
    const beamRefs = useRef<THREE.Mesh[]>([])

    const beams = useMemo<Beam[]>(() => {
        const result: Beam[] = []
        for (let i = 0; i < 6; i++) {
            result.push({
                x: (Math.random() - 0.5) * 14,
                speed: 8 + Math.random() * 15,
                color: BEAM_COLORS[Math.floor(Math.random() * BEAM_COLORS.length)],
                width: 0.02 + Math.random() * 0.03,
                phase: Math.random() * Math.PI * 2,
                height: 3 + Math.random() * 5,
            })
        }
        return result
    }, [])

    useFrame((state) => {
        const t = state.clock.elapsedTime

        beamRefs.current.forEach((mesh, i) => {
            if (!mesh) return
            const beam = beams[i]

            // Beam travels up and down, wrapped around camera view
            const yOffset = ((t * beam.speed + beam.phase * 20) % 40) - 20
            mesh.position.y = elevatorY + yOffset

            // Pulse opacity
            const mat = mesh.material as THREE.MeshStandardMaterial
            mat.emissiveIntensity = 2 + Math.sin(t * 4 + beam.phase) * 1.5
            mat.opacity = 0.3 + Math.sin(t * 3 + beam.phase) * 0.15
        })
    })

    return (
        <group ref={groupRef}>
            {beams.map((beam, i) => (
                <mesh
                    key={i}
                    ref={(el) => { if (el) beamRefs.current[i] = el }}
                    position={[beam.x, 0, -1]}
                >
                    <boxGeometry args={[beam.width, beam.height, beam.width]} />
                    <meshStandardMaterial
                        color="#000000"
                        emissive={beam.color}
                        emissiveIntensity={2}
                        transparent
                        opacity={0.35}
                        depthWrite={false}
                        blending={THREE.AdditiveBlending}
                    />
                </mesh>
            ))}
        </group>
    )
}
