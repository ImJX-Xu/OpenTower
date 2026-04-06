import { useEffect, useRef } from 'react'

const FADE_DURATION = 2 // seconds
const TARGET_VOLUME = 0.35

export function useBackgroundMusic(src: string) {
    const audioRef = useRef<HTMLAudioElement | null>(null)
    const fadeIntervalRef = useRef<number | null>(null)

    useEffect(() => {
        const audio = new Audio(src)
        audio.loop = true
        audio.volume = 0
        audioRef.current = audio

        const fadeIn = () => {
            const steps = FADE_DURATION * 60 // ~60fps
            const increment = TARGET_VOLUME / steps
            let current = 0

            fadeIntervalRef.current = window.setInterval(() => {
                current += increment
                if (current >= TARGET_VOLUME) {
                    audio.volume = TARGET_VOLUME
                    if (fadeIntervalRef.current) clearInterval(fadeIntervalRef.current)
                } else {
                    audio.volume = current
                }
            }, 1000 / 60)
        }

        // Browsers require user interaction before playing audio.
        // We listen for the first click/keydown, then start with a fade-in.
        const startOnInteraction = () => {
            audio.play().then(fadeIn).catch(() => {/* blocked, will retry on next interaction */})
            document.removeEventListener('click', startOnInteraction)
            document.removeEventListener('keydown', startOnInteraction)
            document.removeEventListener('touchstart', startOnInteraction)
        }

        document.addEventListener('click', startOnInteraction)
        document.addEventListener('keydown', startOnInteraction)
        document.addEventListener('touchstart', startOnInteraction)

        return () => {
            document.removeEventListener('click', startOnInteraction)
            document.removeEventListener('keydown', startOnInteraction)
            document.removeEventListener('touchstart', startOnInteraction)
            if (fadeIntervalRef.current) clearInterval(fadeIntervalRef.current)

            // Fade out on unmount
            if (audio && !audio.paused) {
                const steps = FADE_DURATION * 60
                const decrement = audio.volume / steps
                let vol = audio.volume
                const fadeOut = window.setInterval(() => {
                    vol -= decrement
                    if (vol <= 0) {
                        audio.volume = 0
                        audio.pause()
                        clearInterval(fadeOut)
                    } else {
                        audio.volume = vol
                    }
                }, 1000 / 60)
            }
        }
    }, [src])
}
