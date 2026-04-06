'use client'

import {
    EffectComposer,
    Bloom,
    Vignette,
    ChromaticAberration,
} from '@react-three/postprocessing'
import { BlendFunction } from 'postprocessing'
import { Vector2 } from 'three'

export default function Effects() {
    return (
        <EffectComposer>
            <Bloom
                intensity={0.8}
                luminanceThreshold={0.3}
                luminanceSmoothing={0.6}
                mipmapBlur
            />
            <Vignette
                offset={0.3}
                darkness={0.7}
                blendFunction={BlendFunction.NORMAL}
            />
            <ChromaticAberration
                offset={new Vector2(0.0008, 0.0008)}
                blendFunction={BlendFunction.NORMAL}
                radialModulation={false}
                modulationOffset={0.5}
            />
        </EffectComposer>
    )
}
