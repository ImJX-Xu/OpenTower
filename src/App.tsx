import { Suspense, useEffect } from 'react'
import { Canvas } from '@react-three/fiber'
import { useElevator } from './hooks/useElevator'
import Scene from './components/Scene'
import HUD from './components/ui/HUD'
import { buildingName, buildingSubtitle } from './utils/floorConfig'

export default function App() {
    const elevator = useElevator()

    useEffect(() => {
        document.title = `${buildingName} — ${buildingSubtitle}`
    }, [])

    return (
        <>
            <div className="canvas-container">
                <Canvas
                    gl={{
                        antialias: true,
                        alpha: false,
                        powerPreference: 'high-performance',
                        stencil: false,
                        depth: true,
                    }}
                    camera={{
                        fov: 50,
                        near: 0.1,
                        far: 200,
                        position: [0, 2.5, 16],
                    }}
                    dpr={[1, 1.5]}
                    style={{ background: '#020208' }}
                >
                    <Suspense fallback={null}>
                        <Scene elevator={elevator} />
                    </Suspense>
                </Canvas>
            </div>
            <HUD elevator={elevator} />
        </>
    )
}
