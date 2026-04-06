'use client'

import { useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import Building from './Building'
import CityBackground from './CityBackground'
import Starfield from './Starfield'
import NeonLights from './NeonLights'
import DataBeams from './DataBeams'
import Effects from './Effects'
import { ElevatorState } from '../hooks/useElevator'

interface SceneProps {
    elevator: ElevatorState
}

export default function Scene({ elevator }: SceneProps) {
    const { camera } = useThree()

    useFrame(() => {
        const targetY = elevator.elevatorY + 2.5
        camera.position.y += (targetY - camera.position.y) * 0.1
        camera.position.x = 0
        camera.position.z = 20
        camera.lookAt(0, camera.position.y + 0.5, 0)
    })

    return (
        <>
            {/* ===== DRAMATICALLY BOOSTED LIGHTING ===== */}

            {/* Ambient fill */}
            <ambientLight intensity={0.35} color="#9999dd" />

            {/* Primary sun/key light — strong directional */}
            <directionalLight
                position={[15, 50, 20]}
                intensity={0.7}
                color="#ddeeff"
            />

            {/* Secondary warm fill from opposite side */}
            <directionalLight
                position={[-10, 20, 10]}
                intensity={0.3}
                color="#ffddaa"
            />

            {/* Tracking spotlight that follows the elevator */}
            <pointLight
                position={[0, elevator.elevatorY + 2.5, 10]}
                intensity={1.8}
                distance={25}
                color="#ffffff"
            />

            {/* Extra warm point light from below for dramatic uplighting */}
            <pointLight
                position={[0, elevator.elevatorY - 2, 6]}
                intensity={0.8}
                distance={18}
                color="#ffaa66"
            />

            {/* Left neon wash */}
            <pointLight
                position={[-12, elevator.elevatorY + 1, 5]}
                intensity={1.2}
                distance={20}
                color="#ff00ff"
            />

            {/* Right neon wash */}
            <pointLight
                position={[12, elevator.elevatorY + 1, 5]}
                intensity={1.2}
                distance={20}
                color="#00f5ff"
            />

            {/* Fog — exponential for visible volumetric haze */}
            <fogExp2 attach="fog" args={['#020208', 0.008]} />

            {/* Starfield Background (deepest layer) */}
            <Starfield elevatorY={elevator.elevatorY} />

            {/* City Background (parallax) */}
            <CityBackground elevatorY={elevator.elevatorY} />

            {/* Main Building */}
            <Building
                currentFloor={elevator.currentFloor}
                elevatorY={elevator.elevatorY}
                totalFloors={elevator.totalFloors}
            />

            {/* Neon Lights */}
            <NeonLights elevatorY={elevator.elevatorY} totalFloors={elevator.totalFloors} />

            {/* Cross-floor data beams */}
            <DataBeams elevatorY={elevator.elevatorY} totalFloors={elevator.totalFloors} />

            {/* Post-processing Effects */}
            <Effects />
        </>
    )
}
