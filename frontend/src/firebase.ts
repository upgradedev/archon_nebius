import { initializeApp } from 'firebase/app'
import { getAuth, GoogleAuthProvider } from 'firebase/auth'

const firebaseConfig = {
  apiKey: 'AIzaSyDJo0hidUN0YKZYS8g6w2Ca062NgBMn3Ns',
  authDomain: 'archon-pnl.firebaseapp.com',
  projectId: 'archon-pnl',
  storageBucket: 'archon-pnl.firebasestorage.app',
  messagingSenderId: '987324581165',
  appId: '1:987324581165:web:35bc54ca2932359c38bfa4',
}

const app = initializeApp(firebaseConfig)
export const auth = getAuth(app)
export const googleProvider = new GoogleAuthProvider()
