import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  type User,
} from 'firebase/auth'
import { authDevBypass, getFirebaseAuth } from '../firebase'

type AuthContextValue = {
  user: User | null
  loading: boolean
  /** Firebase ID token for API calls; empty string when using dev bypass. */
  getIdToken: () => Promise<string | null>
  signInWithEmail: (email: string, password: string) => Promise<void>
  signUpWithEmail: (email: string, password: string) => Promise<void>
  signInWithGoogle: () => Promise<void>
  logOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(!authDevBypass)

  useEffect(() => {
    if (authDevBypass) {
      setLoading(false)
      return
    }
    const auth = getFirebaseAuth()
    if (!auth) {
      setLoading(false)
      return
    }
    const unsub = onAuthStateChanged(auth, (u) => {
      setUser(u)
      setLoading(false)
    })
    return () => unsub()
  }, [])

  const getIdToken = useCallback(async () => {
    if (authDevBypass) return ''
    if (!user) return null
    return user.getIdToken()
  }, [user])

  const signInWithEmail = useCallback(async (email: string, password: string) => {
    const auth = getFirebaseAuth()
    if (!auth) throw new Error('Firebase Auth not initialized')
    await signInWithEmailAndPassword(auth, email, password)
  }, [])

  const signUpWithEmail = useCallback(async (email: string, password: string) => {
    const auth = getFirebaseAuth()
    if (!auth) throw new Error('Firebase Auth not initialized')
    await createUserWithEmailAndPassword(auth, email, password)
  }, [])

  const signInWithGoogle = useCallback(async () => {
    const auth = getFirebaseAuth()
    if (!auth) throw new Error('Firebase Auth not initialized')
    const provider = new GoogleAuthProvider()
    await signInWithPopup(auth, provider)
  }, [])

  const logOut = useCallback(async () => {
    if (authDevBypass) return
    const auth = getFirebaseAuth()
    if (auth) await signOut(auth)
  }, [])

  const value = useMemo(
    () => ({
      user: authDevBypass ? null : user,
      loading,
      getIdToken,
      signInWithEmail,
      signUpWithEmail,
      signInWithGoogle,
      logOut,
    }),
    [
      user,
      loading,
      getIdToken,
      signInWithEmail,
      signUpWithEmail,
      signInWithGoogle,
      logOut,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
