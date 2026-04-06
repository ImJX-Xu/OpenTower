import * as THREE from 'three'

type WallpaperGenerator = (ctx: CanvasRenderingContext2D, w: number, h: number) => void

const generators: WallpaperGenerator[] = [
    // 0: Circuit Board
    (ctx, w, h) => {
        ctx.fillStyle = '#0a1a0a'
        ctx.fillRect(0, 0, w, h)
        ctx.strokeStyle = '#00ff6644'
        ctx.lineWidth = 1
        for (let i = 0; i < 20; i++) {
            const x = Math.random() * w
            const y = Math.random() * h
            ctx.beginPath()
            ctx.moveTo(x, y)
            ctx.lineTo(x + (Math.random() - 0.5) * 100, y)
            ctx.lineTo(x + (Math.random() - 0.5) * 100, y + (Math.random() - 0.5) * 80)
            ctx.stroke()
            ctx.fillStyle = '#00ff66'
            ctx.fillRect(x - 2, y - 2, 4, 4)
        }
    },

    // 1: Hexagonal Grid
    (ctx, w, h) => {
        ctx.fillStyle = '#0a0a1a'
        ctx.fillRect(0, 0, w, h)
        const size = 20
        ctx.strokeStyle = '#00f5ff22'
        ctx.lineWidth = 0.5
        for (let row = 0; row < h / (size * 1.5); row++) {
            for (let col = 0; col < w / (size * 1.73); col++) {
                const cx = col * size * 1.73 + (row % 2) * size * 0.866
                const cy = row * size * 1.5
                ctx.beginPath()
                for (let i = 0; i < 6; i++) {
                    const angle = (Math.PI / 3) * i - Math.PI / 6
                    const px = cx + size * Math.cos(angle)
                    const py = cy + size * Math.sin(angle)
                    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)
                }
                ctx.closePath()
                ctx.stroke()
            }
        }
    },

    // 2: Matrix Rain
    (ctx, w, h) => {
        ctx.fillStyle = '#000000'
        ctx.fillRect(0, 0, w, h)
        ctx.font = '10px monospace'
        const chars = 'ﾊﾐﾋｰｳｼﾅﾓﾆｻﾜﾂｵﾘｱﾎﾃﾏｹﾒｴｶｷﾑﾕﾗｾﾈｽﾀﾇﾍ012345789ABCDEF'
        for (let x = 0; x < w; x += 12) {
            const len = Math.floor(Math.random() * 15) + 5
            const startY = Math.random() * h
            for (let i = 0; i < len; i++) {
                const alpha = (1 - i / len) * 0.8
                ctx.fillStyle = `rgba(0, 255, 70, ${alpha})`
                const char = chars[Math.floor(Math.random() * chars.length)]
                ctx.fillText(char, x, startY + i * 12)
            }
        }
    },

    // 3: Neon Stripes
    (ctx, w, h) => {
        ctx.fillStyle = '#0a0010'
        ctx.fillRect(0, 0, w, h)
        const colors = ['#ff00ff22', '#00f5ff22', '#ffaa0022']
        for (let y = 0; y < h; y += 8) {
            ctx.fillStyle = colors[Math.floor(y / 8) % colors.length]
            ctx.fillRect(0, y, w, 3)
        }
    },

    // 4: Concrete
    (ctx, w, h) => {
        ctx.fillStyle = '#1a1a1a'
        ctx.fillRect(0, 0, w, h)
        for (let i = 0; i < 2000; i++) {
            const gray = Math.floor(Math.random() * 30 + 15)
            ctx.fillStyle = `rgba(${gray}, ${gray}, ${gray}, 0.3)`
            ctx.fillRect(Math.random() * w, Math.random() * h, 2, 2)
        }
        ctx.strokeStyle = '#22222244'
        ctx.lineWidth = 0.5
        for (let i = 0; i < 5; i++) {
            ctx.beginPath()
            ctx.moveTo(Math.random() * w, Math.random() * h)
            ctx.bezierCurveTo(
                Math.random() * w, Math.random() * h,
                Math.random() * w, Math.random() * h,
                Math.random() * w, Math.random() * h
            )
            ctx.stroke()
        }
    },

    // 5: Japanese Wave
    (ctx, w, h) => {
        ctx.fillStyle = '#0a0a2a'
        ctx.fillRect(0, 0, w, h)
        ctx.strokeStyle = '#4488ff22'
        ctx.lineWidth = 1
        for (let y = 0; y < h; y += 20) {
            for (let x = 0; x < w; x += 30) {
                ctx.beginPath()
                ctx.arc(x + (y % 40 === 0 ? 15 : 0), y, 12, Math.PI, 0)
                ctx.stroke()
            }
        }
    },

    // 6: Cyberpunk Graffiti
    (ctx, w, h) => {
        ctx.fillStyle = '#111115'
        ctx.fillRect(0, 0, w, h)
        const colors = ['#ff00ff', '#00f5ff', '#ff4444', '#ffaa00', '#00ff88']
        for (let i = 0; i < 15; i++) {
            ctx.fillStyle = colors[i % colors.length] + '33'
            const shape = Math.random()
            if (shape < 0.3) {
                ctx.beginPath()
                ctx.arc(Math.random() * w, Math.random() * h, Math.random() * 30 + 10, 0, Math.PI * 2)
                ctx.fill()
            } else if (shape < 0.6) {
                ctx.fillRect(Math.random() * w, Math.random() * h, Math.random() * 60, Math.random() * 20)
            } else {
                ctx.beginPath()
                ctx.moveTo(Math.random() * w, Math.random() * h)
                ctx.lineTo(Math.random() * w, Math.random() * h)
                ctx.lineTo(Math.random() * w, Math.random() * h)
                ctx.closePath()
                ctx.fill()
            }
        }
    },

    // 7: Diamond Plate Metal
    (ctx, w, h) => {
        ctx.fillStyle = '#1a1a22'
        ctx.fillRect(0, 0, w, h)
        for (let y = 0; y < h; y += 16) {
            for (let x = 0; x < w; x += 16) {
                const offset = (y % 32) === 0 ? 0 : 8
                ctx.fillStyle = '#ffffff08'
                ctx.beginPath()
                ctx.moveTo(x + offset, y)
                ctx.lineTo(x + offset + 6, y + 4)
                ctx.lineTo(x + offset, y + 8)
                ctx.lineTo(x + offset - 6, y + 4)
                ctx.closePath()
                ctx.fill()
            }
        }
    },

    // 8: Holographic Gradient
    (ctx, w, h) => {
        const gradient = ctx.createLinearGradient(0, 0, w, h)
        gradient.addColorStop(0, '#ff006622')
        gradient.addColorStop(0.2, '#00f5ff22')
        gradient.addColorStop(0.4, '#ff00ff22')
        gradient.addColorStop(0.6, '#00ff8822')
        gradient.addColorStop(0.8, '#ffaa0022')
        gradient.addColorStop(1, '#ff006622')
        ctx.fillStyle = '#0a0a10'
        ctx.fillRect(0, 0, w, h)
        ctx.fillStyle = gradient
        ctx.fillRect(0, 0, w, h)
        // Add scanlines
        for (let y = 0; y < h; y += 3) {
            ctx.fillStyle = '#00000022'
            ctx.fillRect(0, y, w, 1)
        }
    },

    // 9: Binary Code
    (ctx, w, h) => {
        ctx.fillStyle = '#000a00'
        ctx.fillRect(0, 0, w, h)
        ctx.font = '8px monospace'
        for (let y = 0; y < h; y += 10) {
            for (let x = 0; x < w; x += 7) {
                const alpha = Math.random() * 0.4 + 0.05
                ctx.fillStyle = `rgba(0, 255, 100, ${alpha})`
                ctx.fillText(Math.random() > 0.5 ? '1' : '0', x, y)
            }
        }
    },
]

const textureCache = new Map<string, THREE.CanvasTexture>()

export function getWallpaperTexture(index: number, seed: number = 0): THREE.CanvasTexture {
    const key = `${index}-${seed}`
    if (textureCache.has(key)) {
        return textureCache.get(key)!
    }

    const canvas = document.createElement('canvas')
    canvas.width = 256
    canvas.height = 256
    const ctx = canvas.getContext('2d')!

    const gen = generators[index % generators.length]
    // Use seed to add slight variation
    const origRandom = Math.random
    let seedVal = seed + index * 1000
    Math.random = () => {
        seedVal = (seedVal * 9301 + 49297) % 233280
        return seedVal / 233280
    }
    gen(ctx, 256, 256)
    Math.random = origRandom

    const texture = new THREE.CanvasTexture(canvas)
    texture.wrapS = THREE.RepeatWrapping
    texture.wrapT = THREE.RepeatWrapping
    texture.repeat.set(2, 2)
    textureCache.set(key, texture)
    return texture
}

export const WALLPAPER_COUNT = generators.length
