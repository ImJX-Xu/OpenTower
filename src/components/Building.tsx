'use client'

import { useMemo } from 'react'
import { Text } from '@react-three/drei'
import Floor, { FLOOR_HEIGHT } from './Floor'

interface BuildingProps {
    currentFloor: number
    elevatorY: number
    totalFloors: number
}

const RENDER_RADIUS = 3 // Only render ±3 floors around camera

export default function Building({ currentFloor, elevatorY, totalFloors }: BuildingProps) {
    const visibleFloors = useMemo(() => {
        const floors: Array<{ index: number; y: number }> = []
        for (let i = 1; i <= totalFloors; i++) {
            if (Math.abs(i - currentFloor) <= RENDER_RADIUS) {
                floors.push({
                    index: i,
                    y: (i - 1) * FLOOR_HEIGHT,
                })
            }
        }
        return floors
    }, [currentFloor, totalFloors])

    const buildingWidth = 8 * 2.0 + 1 // 8 cubicles × 2.0 width + margin
    const buildingHeight = totalFloors * FLOOR_HEIGHT

    return (
        <group>
            {/* Ground plane */}
            <mesh position={[0, -0.2, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                <planeGeometry args={[80, 80]} />
                <meshStandardMaterial color="#040408" roughness={0.7} metalness={0.5} />
            </mesh>

            {/* Building exterior frame — left pillar */}
            <mesh position={[-buildingWidth / 2 - 0.15, buildingHeight / 2, 0]}>
                <boxGeometry args={[0.3, buildingHeight + 1, 8.5]} />
                <meshStandardMaterial
                    color="#080810"
                    roughness={0.4}
                    metalness={0.8}
                    transparent
                    opacity={0.85}
                />
            </mesh>

            {/* Building exterior frame — right pillar */}
            <mesh position={[buildingWidth / 2 + 0.15, buildingHeight / 2, 0]}>
                <boxGeometry args={[0.3, buildingHeight + 1, 8.5]} />
                <meshStandardMaterial
                    color="#080810"
                    roughness={0.4}
                    metalness={0.8}
                    transparent
                    opacity={0.85}
                />
            </mesh>

            {/* Exterior neon strips on pillars */}
            <mesh position={[-buildingWidth / 2 - 0.32, buildingHeight / 2, 1.7]}>
                <boxGeometry args={[0.02, buildingHeight + 1, 0.03]} />
                <meshStandardMaterial color="#000" emissive="#ff00ff" emissiveIntensity={1.2} />
            </mesh>
            <mesh position={[buildingWidth / 2 + 0.32, buildingHeight / 2, 1.7]}>
                <boxGeometry args={[0.02, buildingHeight + 1, 0.03]} />
                <meshStandardMaterial color="#000" emissive="#00f5ff" emissiveIntensity={1.2} />
            </mesh>

            {/* Glass walls — back, left, right (not front) */}
            {/* Back wall */}
            <mesh position={[0, buildingHeight / 2, -4]}>
                <boxGeometry args={[buildingWidth + 0.5, buildingHeight + 1, 0.05]} />
                <meshStandardMaterial
                    color="#0a0a20"
                    transparent
                    opacity={0.75}
                    roughness={0.1}
                    metalness={0.3}
                />
            </mesh>
            {/* Left wall */}
            <mesh position={[-buildingWidth / 2 - 0.1, buildingHeight / 2, 0]}>
                <boxGeometry args={[0.05, buildingHeight + 1, 8.5]} />
                <meshStandardMaterial
                    color="#0a0a20"
                    transparent
                    opacity={0.7}
                    roughness={0.1}
                    metalness={0.3}
                />
            </mesh>
            {/* Right wall */}
            <mesh position={[buildingWidth / 2 + 0.1, buildingHeight / 2, 0]}>
                <boxGeometry args={[0.05, buildingHeight + 1, 8.5]} />
                <meshStandardMaterial
                    color="#0a0a20"
                    transparent
                    opacity={0.7}
                    roughness={0.1}
                    metalness={0.3}
                />
            </mesh>

            {/* Render visible floors */}
            {visibleFloors.map((floor) => (
                <Floor
                    key={floor.index}
                    floorIndex={floor.index}
                    yPosition={floor.y}
                    floorActive={Math.abs(floor.index - currentFloor) <= 1}
                />
            ))}

            {/* Roof structure */}
            <group position={[0, buildingHeight, 0]}>
                <mesh position={[0, 0.3, 0]}>
                    <boxGeometry args={[buildingWidth + 1, 0.3, 9]} />
                    <meshStandardMaterial color="#0a0a15" metalness={0.7} roughness={0.3} />
                </mesh>
                {/* Antenna */}
                <mesh position={[0, 3, 0]}>
                    <cylinderGeometry args={[0.03, 0.06, 5, 6]} />
                    <meshStandardMaterial color="#333340" metalness={0.9} />
                </mesh>
                {/* Antenna light */}
                <mesh position={[0, 5.5, 0]}>
                    <sphereGeometry args={[0.08, 8, 8]} />
                    <meshStandardMaterial color="#ff0000" emissive="#ff0000" emissiveIntensity={2} />
                </mesh>
            </group>

            {/* ===== Elevator position indicator — thin rails only ===== */}
            {/* Left rail */}
            <mesh position={[-buildingWidth / 2 - 0.3, buildingHeight / 2, 0]}>
                <boxGeometry args={[0.06, buildingHeight, 0.06]} />
                <meshStandardMaterial color="#111122" roughness={0.8} />
            </mesh>

            {/* Right rail */}
            <mesh position={[buildingWidth / 2 + 0.3, buildingHeight / 2, 0]}>
                <boxGeometry args={[0.06, buildingHeight, 0.06]} />
                <meshStandardMaterial color="#111122" roughness={0.8} />
            </mesh>
        </group>
    )
}
