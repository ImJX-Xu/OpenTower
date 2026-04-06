'use client'

import { useRef, useMemo, memo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

interface CharacterProps {
    position: [number, number, number]
    pose: 'typing' | 'standing' | 'phone' | 'sitting' | 'leaning'
    seed: number
    floorActive: boolean
}

// Seeded random
function seededRandom(seed: number) {
    let s = seed
    return () => {
        s = (s * 16807) % 2147483647
        return (s - 1) / 2147483646
    }
}

// Shared geometries (module-level singletons for performance)
const torsoGeo = new THREE.BoxGeometry(0.3, 0.35, 0.18)
const headGeo = new THREE.SphereGeometry(0.1, 6, 6)
const hairGeo = new THREE.SphereGeometry(0.09, 6, 4, 0, Math.PI * 2, 0, Math.PI / 2)
const armGeo = new THREE.BoxGeometry(0.08, 0.25, 0.08)
const handGeo = new THREE.SphereGeometry(0.035, 4, 4)
const legGeo = new THREE.BoxGeometry(0.1, 0.34, 0.1)

const hairMat = new THREE.MeshStandardMaterial({ color: '#1a1a1a', roughness: 0.9 })
const pantsMat = new THREE.MeshStandardMaterial({ color: '#1a1a2a', roughness: 0.8 })

const SKIN_COLORS = ['#e8b89a', '#c48a6a', '#8d5524', '#f5d0a9', '#d4a57b']
const SHIRT_COLORS = ['#1a3a5c', '#3c1a5c', '#5c1a2a', '#1a5c3a', '#4a4a5c']

/**
 * Character — Low-poly humanoid figure.
 * Memo'd with shared geometries for performance.
 * Throttled animation (~15fps).
 */
const Character = memo(function Character({ position, seed, floorActive }: CharacterProps) {
    const headRef = useRef<THREE.Group>(null)
    const leftArmRef = useRef<THREE.Group>(null)
    const rightArmRef = useRef<THREE.Group>(null)
    const frameCountRef = useRef(0)

    const data = useMemo(() => {
        const rand = seededRandom(seed)
        return {
            skinMat: new THREE.MeshStandardMaterial({
                color: SKIN_COLORS[Math.floor(rand() * SKIN_COLORS.length)],
                roughness: 0.7,
            }),
            shirtMat: new THREE.MeshStandardMaterial({
                color: SHIRT_COLORS[Math.floor(rand() * SHIRT_COLORS.length)],
                roughness: 0.8,
            }),
            animSpeed: 1.5 + rand() * 2,
            animStyle: Math.floor(rand() * 3),
        }
    }, [seed])

    // Throttled animation (~15fps instead of 60fps)
    useFrame(({ clock }) => {
        if (!floorActive) return

        frameCountRef.current++
        if (frameCountRef.current % 4 !== 0) return // Skip 3 of every 4 frames

        const t = clock.elapsedTime * data.animSpeed

        // Head look-around
        if (headRef.current) {
            headRef.current.rotation.y = Math.sin(t * 0.4) * 0.1
            headRef.current.rotation.x = Math.sin(t * 0.3) * 0.05 - 0.1
        }

        // Arm animation based on style
        if (data.animStyle === 0) {
            // Typing animation
            if (leftArmRef.current) {
                leftArmRef.current.rotation.x = -Math.PI / 3 + Math.sin(t * 3) * 0.08
            }
            if (rightArmRef.current) {
                rightArmRef.current.rotation.x = -Math.PI / 3 + Math.sin(t * 3.5 + 1) * 0.08
            }
        } else if (data.animStyle === 2 && rightArmRef.current) {
            // Phone pose
            rightArmRef.current.rotation.x = -Math.PI / 2.2
            rightArmRef.current.rotation.z = -0.3
        }
    })

    return (
        <group position={position}>
            {/* Torso */}
            <mesh position={[0, 0.72, 0]} geometry={torsoGeo} material={data.shirtMat} />

            {/* Head */}
            <group ref={headRef} position={[0, 1.02, 0]}>
                <mesh geometry={headGeo} material={data.skinMat} />
                <mesh position={[0, 0.06, -0.02]} geometry={hairGeo} material={hairMat} />
            </group>

            {/* Left Arm */}
            <group ref={leftArmRef} position={[-0.22, 0.55, 0]}>
                <mesh position={[0, -0.12, 0]} geometry={armGeo} material={data.shirtMat} />
                <mesh position={[0, -0.26, 0.02]} geometry={handGeo} material={data.skinMat} />
            </group>

            {/* Right Arm */}
            <group ref={rightArmRef} position={[0.22, 0.55, 0]}>
                <mesh position={[0, -0.12, 0]} geometry={armGeo} material={data.shirtMat} />
                <mesh position={[0, -0.26, 0.02]} geometry={handGeo} material={data.skinMat} />
            </group>

            {/* Legs */}
            <mesh position={[-0.08, 0.28, 0.05]} geometry={legGeo} material={pantsMat} />
            <mesh position={[0.08, 0.28, 0.05]} geometry={legGeo} material={pantsMat} />
        </group>
    )
})

export default Character
