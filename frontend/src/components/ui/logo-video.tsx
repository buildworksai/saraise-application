/**
 * SPDX-License-Identifier: Apache-2.0
 */
import { useState, useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'

interface LogoVideoProps {
  /**
   * Width of the video/logo
   */
  width?: number | string
  /**
   * Height of the video/logo
   */
  height?: number | string
  /**
   * Show text label below logo
   */
  showText?: boolean
  /**
   * Custom className
   */
  className?: string
  /**
   * Alt text for accessibility
   */
  alt?: string
  /**
   * Whether to autoplay the video
   */
  autoplay?: boolean
  /**
   * Whether to loop the video
   */
  loop?: boolean
  /**
   * Render as full-bleed background (object-cover)
   */
  background?: boolean
}

/**
 * Logo Video Component
 *
 * Displays the SARAISE logo animation (pre-merged video loop)
 * Falls back to static logo image if video fails to load or bandwidth is low
 */
export function LogoVideo({
  width = 120,
  height,
  showText = false,
  className,
  alt = 'SARAISE - Secure and Reliable AI Symphony ERP',
  autoplay = true,
  loop = true,
  background = false,
}: LogoVideoProps) {
  const [videoError, setVideoError] = useState(false)
  const [showFallback, setShowFallback] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const fallbackTimeoutRef = useRef<ReturnType<typeof setTimeout>>()

  const videoSrc = '/videos/saraise-logo-loop.mp4'

  const logoSrc = '/logos/logo.png'

  // Calculate height based on logo aspect ratio if not provided
  const logoAspectRatio = 172 / 256
  const calculatedHeight = height ?? (typeof width === 'number' ? width / logoAspectRatio : 'auto')

  useEffect(() => {
    // Set a timeout to show fallback if video takes too long to load (bandwidth issue)
    if (autoplay && !videoError) {
      fallbackTimeoutRef.current = setTimeout(() => {
        if (videoRef.current && videoRef.current.readyState < 2) {
          setShowFallback(true)
        }
      }, 3000) // 3 second timeout
    }

    return () => {
      if (fallbackTimeoutRef.current) {
        clearTimeout(fallbackTimeoutRef.current)
      }
    }
  }, [autoplay, videoError])

  const handleVideoError = () => {
    setVideoError(true)
    setShowFallback(true)
  }

  const handleVideoCanPlay = () => {
    if (fallbackTimeoutRef.current) {
      clearTimeout(fallbackTimeoutRef.current)
    }
    setShowFallback(false)
  }

  // Show fallback if video error or timeout
  const wrapperClass = background ? 'absolute inset-0' : 'flex flex-col items-center'
  const mediaClass = background
    ? cn('absolute inset-0 w-full h-full object-cover pointer-events-none', className)
    : cn('object-contain max-w-full h-auto', className)

  if (showFallback || videoError) {
    return (
      <div className={cn(wrapperClass)}>
        <img
          src={logoSrc}
          alt={alt}
          width={background ? '100%' : width}
          height={background ? '100%' : calculatedHeight}
          className={mediaClass}
          loading="eager"
        />
        {showText && (
          <span className={cn(
            'mt-2 text-sm font-semibold',
            className?.includes('text-white') ? 'text-white' : 'text-foreground'
          )}>
            SARAISE
          </span>
        )}
      </div>
    )
  }

  return (
    <div className={cn(wrapperClass)}>
      <video
        ref={videoRef}
        src={videoSrc}
        width={background ? '100%' : width}
        height={background ? '100%' : calculatedHeight}
        className={mediaClass}
        autoPlay={autoplay}
        muted
        playsInline
        loop={loop}
        preload="auto"
        onError={handleVideoError}
        onCanPlay={handleVideoCanPlay}
        onLoadedData={handleVideoCanPlay}
        onStalled={() => {
          if (videoRef.current && !videoRef.current.ended) {
            videoRef.current.play().catch(() => {
              setShowFallback(true)
            })
          }
        }}
      >
        {/* Fallback to static logo if video not supported */}
        <img
          src={logoSrc}
          alt={alt}
          width={width}
          height={calculatedHeight}
          className="object-contain max-w-full h-auto"
        />
      </video>
      {showText && (
        <span className={cn(
          'mt-2 text-sm font-semibold',
          className?.includes('text-white') ? 'text-white' : 'text-foreground'
        )}>
          SARAISE
        </span>
      )}
    </div>
  )
}
