'use client'

import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Text } from '@react-three/drei'
import * as THREE from 'three'
import { buildingName } from '../utils/floorConfig'

interface NeonLightsProps {
    elevatorY: number
    totalFloors: number
}

export default function NeonLights({ elevatorY, totalFloors }: NeonLightsProps) {
    const sign1Ref = useRef<THREE.Mesh>(null)
    const sign2Ref = useRef<THREE.Mesh>(null)
    const sign3Ref = useRef<THREE.Mesh>(null)

    useFrame((state) => {
        const t = state.clock.elapsedTime

        if (sign1Ref.current) {
            const mat = sign1Ref.current.material as THREE.MeshStandardMaterial
            mat.emissiveIntensity = 1.5 + Math.sin(t * 2) * 0.8
        }
        if (sign2Ref.current) {
            const mat = sign2Ref.current.material as THREE.MeshStandardMaterial
            mat.emissiveIntensity = 1.8 + Math.sin(t * 1.5 + 1) * 0.8
        }
        if (sign3Ref.current) {
            const mat = sign3Ref.current.material as THREE.MeshStandardMaterial
            mat.emissiveIntensity = Math.random() > 0.95 ? 0.3 : 1.5 + Math.sin(t * 3) * 0.6
        }
    })

    const buildingWidth = 8 * 2.0 + 1
    const topY = totalFloors * 4.0

    return (
        <group>
            {/* Top sign - Building Name */}
            <group position={[0, topY + 2.5, 2.5]}>
                <mesh position={[0, 0, -0.1]}>
                    <boxGeometry args={[10, 3, 0.1]} />
                    <meshStandardMaterial color="#050505" roughness={0.9} />
                </mesh>
                <mesh ref={sign1Ref}>
                    <boxGeometry args={[8, 1.2, 0.05]} />
                    <meshStandardMaterial
                        color="#000"
                        emissive="#ff00ff"
                        emissiveIntensity={2}
                    />
                </mesh>
                {/* Building name */}
                <Text
                    position={[0, 0, 0.06]}
                    fontSize={0.7}
                    color="#ffffff"
                    anchorX="center"
                    anchorY="middle"
                    letterSpacing={0.4}
                >
                    {buildingName}
                </Text>
                <mesh position={[0, -1.0, 0]}>
                    <boxGeometry args={[8, 0.08, 0.05]} />
                    <meshStandardMaterial
                        color="#000"
                        emissive="#00f5ff"
                        emissiveIntensity={1.5}
                    />
                </mesh>
            </group>

            {/* Side sign - left, follows camera */}
            <mesh
                ref={sign2Ref}
                position={[-buildingWidth / 2 - 0.6, elevatorY + 2, 2.5]}
                rotation={[0, 0, Math.PI / 2]}
            >
                <boxGeometry args={[3, 0.4, 0.05]} />
                <meshStandardMaterial
                    color="#000"
                    emissive="#00f5ff"
                    emissiveIntensity={1.8}
                />
            </mesh>

            {/* Side sign - right, follows camera */}
            <mesh
                ref={sign3Ref}
                position={[buildingWidth / 2 + 0.6, elevatorY + 2, 2.5]}
                rotation={[0, 0, Math.PI / 2]}
            >
                <boxGeometry args={[3, 0.4, 0.05]} />
                <meshStandardMaterial
                    color="#000"
                    emissive="#ffaa00"
                    emissiveIntensity={1.5}
                />
            </mesh>

            {/* Moving point lights — boosted */}
            <pointLight
                color="#ff00ff"
                intensity={4}
                distance={25}
                position={[-buildingWidth / 2 - 2, elevatorY, 4]}
            />
            <pointLight
                color="#00f5ff"
                intensity={4}
                distance={25}
                position={[buildingWidth / 2 + 2, elevatorY, 4]}
            />

            {/* Top beacon light */}
            <pointLight
                color="#ff00ff"
                intensity={6}
                distance={30}
                position={[0, topY + 3, 3]}
            />
        </group>
    )
}
