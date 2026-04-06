'use client'

import { useMemo } from 'react'
import { Text } from '@react-three/drei'
import Cubicle from './Cubicle'
import { getFloorName } from '../utils/floorConfig'

interface FloorProps {
    floorIndex: number
    yPosition: number
    floorActive: boolean
}

const COLS = 8        // 8 cubicles wide
const ROWS = 3        // 3 rows deep
const CUBICLE_W = 2.0 // width per cubicle
const CUBICLE_D = 2.5 // depth per cubicle
const FLOOR_HEIGHT = 4.0

export default function Floor({ floorIndex, yPosition, floorActive }: FloorProps) {
    const totalWidth = COLS * CUBICLE_W
    const totalDepth = ROWS * CUBICLE_D

    const cubicles = useMemo(() => {
        const items: Array<{
            key: string
            position: [number, number, number]
            col: number
            row: number
        }> = []
        for (let row = 0; row < ROWS; row++) {
            for (let col = 0; col < COLS; col++) {
                items.push({
                    key: `c-${floorIndex}-${row}-${col}`,
                    position: [
                        (col - (COLS - 1) / 2) * CUBICLE_W,
                        0,
                        (row - (ROWS - 1) / 2) * CUBICLE_D,
                    ],
                    col,
                    row,
                })
            }
        }
        return items
    }, [floorIndex])

    return (
        <group position={[0, yPosition, 0]}>
            {/* Floor slab — dark grated metal */}
            <mesh position={[0, -0.06, 0]}>
                <boxGeometry args={[totalWidth + 1, 0.12, totalDepth + 1]} />
                <meshStandardMaterial color="#060610" roughness={0.6} metalness={0.7} />
            </mesh>

            {/* Data conduit — front edge */}
            <mesh position={[0, 0.02, totalDepth / 2 + 0.3]}>
                <boxGeometry args={[totalWidth * 0.9, 0.04, 0.06]} />
                <meshStandardMaterial color="#000" emissive="#00f5ff" emissiveIntensity={0.4} />
            </mesh>
            {/* Data conduit — back edge */}
            <mesh position={[0, 0.02, -totalDepth / 2 - 0.3]}>
                <boxGeometry args={[totalWidth * 0.9, 0.04, 0.06]} />
                <meshStandardMaterial color="#000" emissive="#ff00ff" emissiveIntensity={0.3} />
            </mesh>

            {/* Ceiling slab */}
            <mesh position={[0, FLOOR_HEIGHT - 0.06, 0]}>
                <boxGeometry args={[totalWidth + 1, 0.12, totalDepth + 1]} />
                <meshStandardMaterial color="#060610" roughness={0.8} metalness={0.4} />
            </mesh>

            {/* Ceiling light strips — cold industrial blue-white */}
            {Array.from({ length: 4 }, (_, i) => {
                const xPos = (i - 1.5) * (CUBICLE_W * 2)
                return (
                    <mesh key={`light-${i}`} position={[xPos, FLOOR_HEIGHT - 0.12, 0]}>
                        <boxGeometry args={[0.15, 0.06, totalDepth * 0.9]} />
                        <meshStandardMaterial
                            color="#ffffff"
                            emissive="#aabbff"
                            emissiveIntensity={0.8}
                        />
                    </mesh>
                )
            })}

            {/* Floor number neon indicator */}
            <mesh position={[-totalWidth / 2 - 0.45, FLOOR_HEIGHT / 2, 0]}>
                <boxGeometry args={[0.05, 0.5, 0.8]} />
                <meshStandardMaterial
                    color="#000000"
                    emissive={floorActive ? '#00f5ff' : '#002233'}
                    emissiveIntensity={floorActive ? 1.2 : 0.2}
                />
            </mesh>

            {/* Department name label — floating in center of floor */}
            <group position={[0, FLOOR_HEIGHT / 2, totalDepth / 2 + 1.5]}>
                {/* Backplate */}
                <mesh position={[0, 0, -0.05]}>
                    <boxGeometry args={[4, 0.8, 0.02]} />
                    <meshStandardMaterial
                        color="#050508"
                        transparent
                        opacity={0.7}
                    />
                </mesh>
                <Text
                    fontSize={0.35}
                    color="#00f5ff"
                    anchorX="center"
                    anchorY="middle"
                    letterSpacing={0.15}
                >
                    {`F${floorIndex} · ${getFloorName(floorIndex)}`}
                </Text>
            </group>

            {/* Cubicles — 10×3 grid of desks with people */}
            {cubicles.map((c) => (
                <Cubicle
                    key={c.key}
                    position={c.position}
                    col={c.col}
                    row={c.row}
                    floorIndex={floorIndex}
                    floorActive={floorActive}
                />
            ))}
        </group>
    )
}

export { FLOOR_HEIGHT }
