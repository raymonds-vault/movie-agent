import { initializeApp, type FirebaseApp } from 'firebase/app'
import { getAnalytics, isSupported, type Analytics } from 'firebase/analytics'
import { getAuth, type Auth } from 'firebase/auth'

/** When true (and backend AUTH_DEV_BYPASS), skip Firebase client init. */
export const authDevBypass =
  import.meta.env.VITE_AUTH_DEV_BYPASS === 'true' ||
  import.meta.env.VITE_AUTH_DEV_BYPASS === '1'

let app: FirebaseApp | null = null
let analyticsInstance: Analytics | null | undefined

function buildFirebaseConfig() {
  const apiKey = import.meta.env.VITE_FIREBASE_API_KEY
  if (!apiKey) return null
  const measurementId = import.meta.env.VITE_FIREBASE_MEASUREMENT_ID
  return {
    apiKey,
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
    storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
    appId: import.meta.env.VITE_FIREBASE_APP_ID,
    ...(measurementId ? { measurementId } : {}),
  }
}

export function getFirebaseApp(): FirebaseApp | null {
  if (authDevBypass) return null
  const config = buildFirebaseConfig()
  if (!config) {
    console.warn(
      'VITE_FIREBASE_* not set. Set VITE_AUTH_DEV_BYPASS=true for local bypass or add Firebase web config.',
    )
    return null
  }
  if (!app) {
    app = initializeApp(config)
  }
  return app
}

/**
 * Firebase Analytics (browser only). Call after app init; no-ops on SSR or unsupported.
 */
export async function getFirebaseAnalytics(): Promise<Analytics | null> {
  if (authDevBypass || typeof window === 'undefined') return null
  const a = getFirebaseApp()
  if (!a) return null
  if (analyticsInstance !== undefined) return analyticsInstance
  const mid = import.meta.env.VITE_FIREBASE_MEASUREMENT_ID
  if (!mid) {
    analyticsInstance = null
    return null
  }
  try {
    const ok = await isSupported()
    if (!ok) {
      analyticsInstance = null
      return null
    }
    analyticsInstance = getAnalytics(a)
    return analyticsInstance
  } catch {
    analyticsInstance = null
    return null
  }
}

export function getFirebaseAuth(): Auth | null {
  const firebaseApp = getFirebaseApp()
  if (!firebaseApp) return null
  return getAuth(firebaseApp)
}
