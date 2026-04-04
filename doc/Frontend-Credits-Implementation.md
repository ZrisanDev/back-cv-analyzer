# Frontend Implementation Guide - Credits & Payments System

> CV Analyzer - Sistema de Créditos y Pagos con MercadoPago
>
> Documento de referencia para implementar el flujo de pagos en el frontend.

---

## 📋 Tabla de Contenidos

1. [Descripción General](#descripción-general)
2. [Arquitectura de Créditos](#arquitectura-de-créditos)
3. [Endpoints API Disponibles](#endpoints-api-disponibles)
4. [Componentes Requeridos](#componentes-requeridos)
5. [Flujo de Usuario](#flujo-de-usuario)
6. [Implementación Detallada](#implementación-detallada)
7. [Manejo de Errores](#manejo-de-errores)
8. [Pruebas y QA](#pruebas-y-qa)

---

## 🎯 Descripción General

El sistema de créditos permite a los usuarios comprar paquetes de análisis (20, 50, 100) para usar después de agotar sus 3 análisis gratuitos.

**Puntos clave:**
- Los primeros 3 análisis son gratuitos
- Los créditos pagos **no expiran**
- Precios en USD con conversión automática por MercadoPago
- El usuario siempre ve su saldo disponible

---

## 💰 Arquitectura de Créditos

### Tipos de Créditos

```
Usuario {
  free_analyses_count: 3,        // Análisis gratis usados (máx: 3)
  paid_analyses_credits: 50,       // Créditos pagos disponibles
  total_analyses_used: 8,          // Total análisis realizados
}
```

### Paquetes Disponibles

| Paquete | Créditos | Precio USD | Precio/Crédito |
|---------|-----------|-------------|-----------------|
| Pack 20 | 20 | $3.00 | $0.15 |
| Pack 50 | 50 | $10.00 | $0.20 |
| Pack 100 | 100 | $20.00 | $0.20 |

### Reglas de Consumo

1. Prioridad: Análisis gratis primero → Créditos pagos después
2. Sin créditos: El backend devuelve `402 Payment Required`
3. Header especial: `X-Needs-Payment: true` indica falta de créditos

---

## 🔌 Endpoints API Disponibles

### Obtener Créditos del Usuario

**Endpoint:** `GET /api/payments/my-credits`

**Headers:**
```
Authorization: Bearer {JWT_TOKEN}
```

**Response (200):**
```json
{
  "free_analyses_count": 3,
  "free_analyses_limit": 3,
  "free_analyses_remaining": 0,
  "paid_analyses_credits": 50,
  "total_analyses_used": 3
}
```

### Obtener Paquetes Disponibles

**Endpoint:** `GET /api/payments/credit-packages`

**Headers:**
```
Authorization: Bearer {JWT_TOKEN}
```

**Response (200):**
```json
[
  {
    "package_type": "pack_20",
    "credits_count": 20,
    "price_usd": 3.0,
    "is_active": true
  },
  {
    "package_type": "pack_50",
    "credits_count": 50,
    "price_usd": 10.0,
    "is_active": true
  },
  {
    "package_type": "pack_100",
    "credits_count": 100,
    "price_usd": 20.0,
    "is_active": true
  }
]
```

### Crear Preferencia de Pago

**Endpoint:** `POST /api/payments/create-package-preference`

**Headers:**
```
Authorization: Bearer {JWT_TOKEN}
Content-Type: application/json
```

**Body:**
```json
{
  "package_type": "pack_50"
}
```

**Response (201):**
```json
{
  "preference_id": "123456789",
  "payment_url": "https://www.mercadopago.com.ar/checkout/v1/...",
  "amount": 10.0,
  "currency": "USD",
  "package_type": "pack_50"
}
```

### Obtener Detalles de Pago

**Endpoint:** `GET /api/payments/{payment_id}`

**Headers:**
```
Authorization: Bearer {JWT_TOKEN}
```

**Response (200):**
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "amount": 10.0,
  "currency": "USD",
  "status": "approved",
  "package_type": "pack_50",
  "created_at": "2026-04-03T10:00:00Z",
  "updated_at": "2026-04-03T10:05:00Z"
}
```

---

## 🧩 Componentes Requeridos

### 1. CreditBadge (Componente de UI)

**Propósito:** Mostrar el saldo de créditos del usuario.

**Ubicación sugerida:** Header/Navbar, Dashboard, Página de análisis.

**Props:**
```typescript
interface CreditBadgeProps {
  free_analyses_remaining: number;
  paid_analyses_credits: number;
  total_credits_available: number; // free_remaining + paid
}
```

**Ejemplo:**
```tsx
<CreditBadge
  free_analyses_remaining={0}
  paid_analyses_credits={50}
  total_credits_available={50}
/>
```

**Visual sugerido:**
```
┌─────────────────────────────┐
│ 💰 50 análisis disponibles │
│ (0 gratis + 50 pagos)  │
└─────────────────────────────┘
```

### 2. PricingCard (Componente de UI)

**Propósito:** Mostrar un paquete de créditos con opción de compra.

**Props:**
```typescript
interface PricingCardProps {
  package_type: 'pack_20' | 'pack_50' | 'pack_100';
  credits_count: number;
  price_usd: number;
  is_popular?: boolean;
  onSelect: (packageType: string) => void;
}
```

**Ejemplo:**
```tsx
<PricingCard
  package_type="pack_50"
  credits_count={50}
  price_usd={10}
  is_popular={true}
  onSelect={(type) => handlePurchase(type)}
/>
```

### 3. PricingPage (Página completa)

**Propósito:** Mostrar todos los paquetes disponibles y permitir la compra.

**Funcionalidades:**
- Fetch de `/api/payments/credit-packages`
- Mostrar los 3 paquetes en grid
- Destacar el paquete "Pack 50" como más popular
- Botón de compra para cada paquete

### 4. PaymentInterceptor (Middleware/Hook)

**Propósito:** Detectar cuando el usuario necesita créditos y redirigir.

**Lógica:**
```typescript
// Interceptar todas las respuestas HTTP
if (response.status === 402 && response.headers.get('X-Needs-Payment') === 'true') {
  // Redirigir a página de pricing
  router.push('/pricing');
}
```

### 5. CreditModal (Modal emergente)

**Propósito:** Mostrar cuando el usuario intenta hacer un análisis sin créditos.

**Funcionalidades:**
- Mensaje amigable explicando por qué necesita comprar
- Botón "Ir a Pricing" → Redirige a `/pricing`
- Botón "Cancelar" → Cierra modal

---

## 🔄 Flujo de Usuario

### Flujo Normal (con créditos)

```
1. Usuario se loguea
   ↓
2. CreditBadge muestra: "53 análisis disponibles (3 gratis + 50 pagos)"
   ↓
3. Usuario sube CV y oferta de trabajo
   ↓
4. POST /api/analysis/submit → 202 Accepted
   ↓
5. Background: polling de /api/analysis/{id}/status
   ↓
6. CreditBadge actualiza: "52 análisis disponibles"
```

### Flujo Sin Créditos

```
1. Usuario agotó los 3 análisis gratis
   ↓
2. CreditBadge muestra: "0 análisis disponibles"
   ↓
3. Usuario intenta subir CV
   ↓
4. POST /api/analysis/submit → 402 Payment Required
   ↓
5. PaymentInterceptor detecta: X-Needs-Payment: true
   ↓
6. CreditModal aparece: "¡Ya usaste tus 3 análisis gratis!"
   ↓
7. Usuario clickea "Comprar créditos"
   ↓
8. Router.push('/pricing')
```

### Flujo de Compra

```
1. Usuario en /pricing
   ↓
2. Fetch: GET /api/payments/credit-packages
   ↓
3. Render: 3 PricingCards
   ↓
4. Usuario elige Pack 50 → clickea "Comprar"
   ↓
5. POST /api/payments/create-package-preference { "package_type": "pack_50" }
   ↓
6. Response: { "payment_url": "https://..." }
   ↓
7. Redirigir: window.location.href = payment_url
   ↓
8. MercadoPago checkout
   ↓
9. Usuario paga → Aprobado
   ↓
10. MercadoPago redirige a frontend con parámetros:
    - ?status=approved (o failure, pending)
    - ?preference_id=...
   ↓
11. Frontend detecta status=approved
    ↓
12. Fetch: GET /api/payments/my-credits (para actualizar UI)
    ↓
13. CreditBadge muestra: "50 análisis disponibles"
```

---

## 🛠️ Implementación Detallada

### 1. Servicio de Créditos (credits.service.ts)

```typescript
// services/credits.service.ts

import apiClient from './api-client';

export interface UserCredits {
  free_analyses_count: number;
  free_analyses_limit: number;
  free_analyses_remaining: number;
  paid_analyses_credits: number;
  total_analyses_used: number;
}

export interface CreditPackage {
  package_type: 'pack_20' | 'pack_50' | 'pack_100';
  credits_count: number;
  price_usd: number;
  is_active: boolean;
}

export interface PaymentPreference {
  preference_id: string;
  payment_url: string;
  amount: number;
  currency: string;
  package_type: string;
}

export const creditsService = {
  // Obtener créditos del usuario
  async getCredits(): Promise<UserCredits> {
    const response = await apiClient.get('/api/payments/my-credits');
    return response.data;
  },

  // Obtener paquetes disponibles
  async getPackages(): Promise<CreditPackage[]> {
    const response = await apiClient.get('/api/payments/credit-packages');
    return response.data;
  },

  // Crear preferencia de pago
  async createPaymentPreference(packageType: string): Promise<PaymentPreference> {
    const response = await apiClient.post('/api/payments/create-package-preference', {
      package_type: packageType,
    });
    return response.data;
  },

  // Obtener detalles de un pago
  async getPayment(paymentId: string): Promise<any> {
    const response = await apiClient.get(`/api/payments/${paymentId}`);
    return response.data;
  },
};
```

### 2. API Client con Interceptor (api-client.ts)

```typescript
// api-client.ts

import axios from 'axios';
import { useRouter } from 'next/navigation';

const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Agregar token JWT a cada request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor de respuestas - detectar falta de créditos
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 402) {
      const needsPayment = error.response.headers['x-needs-payment'];
      if (needsPayment === 'true') {
        // Redirigir a pricing
        window.location.href = '/pricing';
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

### 3. Componente CreditBadge (components/CreditBadge.tsx)

```tsx
// components/CreditBadge.tsx

interface CreditBadgeProps {
  free_analyses_remaining: number;
  paid_analyses_credits: number;
}

export function CreditBadge({ free_analyses_remaining, paid_analyses_credits }: CreditBadgeProps) {
  const totalCredits = free_analyses_remaining + paid_analyses_credits;

  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-blue-50 rounded-lg">
      <span className="text-2xl">💰</span>
      <div className="flex flex-col">
        <span className="text-sm font-semibold text-blue-900">
          {totalCredits} análisis {totalCredits === 1 ? 'disponible' : 'disponibles'}
        </span>
        <span className="text-xs text-blue-600">
          ({free_analyses_remaining} gratis + {paid_analyses_credits} pagos)
        </span>
      </div>
    </div>
  );
}
```

### 4. Componente PricingCard (components/PricingCard.tsx)

```tsx
// components/PricingCard.tsx

interface PricingCardProps {
  package_type: 'pack_20' | 'pack_50' | 'pack_100';
  credits_count: number;
  price_usd: number;
  is_popular?: boolean;
  onSelect: (type: string) => void;
}

export function PricingCard({
  package_type,
  credits_count,
  price_usd,
  is_popular = false,
  onSelect,
}: PricingCardProps) {
  const pricePerCredit = (price_usd / credits_count).toFixed(2);

  return (
    <div
      className={`
        p-6 rounded-2xl border-2 transition-all
        ${is_popular ? 'border-blue-500 shadow-xl scale-105' : 'border-gray-200 hover:border-blue-300'}
      `}
    >
      {is_popular && (
        <div className="bg-blue-500 text-white text-xs font-bold px-3 py-1 rounded-full text-center mb-4">
          MÁS POPULAR
        </div>
      )}

      <h3 className="text-2xl font-bold text-gray-900 mb-2">
        Pack {credits_count}
      </h3>
      <div className="text-4xl font-bold text-blue-600 mb-4">
        ${price_usd.toFixed(2)} USD
      </div>
      <p className="text-sm text-gray-600 mb-6">
        ${pricePerCredit} por análisis
      </p>

      <ul className="space-y-2 mb-6">
        <li className="flex items-center gap-2 text-sm text-gray-700">
          <span>✓</span>
          {credits_count} análisis de CV
        </li>
        <li className="flex items-center gap-2 text-sm text-gray-700">
          <span>✓</span>
          Sin fecha de expiración
        </li>
        <li className="flex items-center gap-2 text-sm text-gray-700">
          <span>✓</span>
          Acceso inmediato
        </li>
      </ul>

      <button
        onClick={() => onSelect(package_type)}
        className={`
          w-full py-3 px-6 rounded-lg font-semibold transition-colors
          ${is_popular
            ? 'bg-blue-600 hover:bg-blue-700 text-white'
            : 'bg-gray-100 hover:bg-gray-200 text-gray-900'
          }
        `}
      >
        Comprar Ahora
      </button>
    </div>
  );
}
```

### 5. Página de Pricing (app/pricing/page.tsx)

```tsx
// app/pricing/page.tsx

'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { creditsService, CreditPackage, PaymentPreference } from '@/services/credits.service';
import { PricingCard } from '@/components/PricingCard';

export default function PricingPage() {
  const router = useRouter();
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadPackages();
  }, []);

  const loadPackages = async () => {
    try {
      const data = await creditsService.getPackages();
      setPackages(data);
    } catch (error) {
      console.error('Error loading packages:', error);
    } finally {
      setLoading(false);
    }
  };

  const handlePurchase = async (packageType: string) => {
    try {
      const preference: PaymentPreference = await creditsService.createPaymentPreference(packageType);

      // Redirigir a MercadoPago
      window.location.href = preference.payment_url;
    } catch (error) {
      console.error('Error creating payment preference:', error);
      alert('Error al iniciar el pago. Por favor intenta nuevamente.');
    }
  };

  if (loading) {
    return <div className="flex justify-center items-center min-h-screen">Cargando...</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            Elige tu Paquete de Análisis
          </h1>
          <p className="text-lg text-gray-600">
            Obtén más análisis para mejorar tu CV y aumentar tus chances
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {packages.map((pkg) => (
            <PricingCard
              key={pkg.package_type}
              package_type={pkg.package_type}
              credits_count={pkg.credits_count}
              price_usd={pkg.price_usd}
              is_popular={pkg.package_type === 'pack_50'}
              onSelect={handlePurchase}
            />
          ))}
        </div>

        <div className="mt-12 text-center text-sm text-gray-500">
          <p>✓ Pagos seguros con MercadoPago</p>
          <p>✓ Conversión automática a tu moneda local</p>
          <p>✓ Los créditos nunca expiran</p>
        </div>
      </div>
    </div>
  );
}
```

### 6. Integración en Header/Navbar (components/Header.tsx)

```tsx
// components/Header.tsx

'use client';

import { useEffect, useState } from 'react';
import { creditsService, UserCredits } from '@/services/credits.service';
import { CreditBadge } from './CreditBadge';

export function Header() {
  const [credits, setCredits] = useState<UserCredits | null>(null);

  useEffect(() => {
    loadCredits();
  }, []);

  const loadCredits = async () => {
    try {
      const data = await creditsService.getCredits();
      setCredits(data);
    } catch (error) {
      console.error('Error loading credits:', error);
    }
  };

  return (
    <header className="bg-white shadow-sm border-b">
      <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <span className="text-2xl">📄</span>
          <span className="text-xl font-bold text-gray-900">CV Analyzer</span>
        </div>

        {/* Navigation */}
        <nav className="flex items-center gap-6">
          <a href="/dashboard" className="text-gray-700 hover:text-gray-900">
            Dashboard
          </a>
          <a href="/history" className="text-gray-700 hover:text-gray-900">
            Historial
          </a>

          {/* Credit Badge */}
          {credits && (
            <CreditBadge
              free_analyses_remaining={credits.free_analyses_remaining}
              paid_analyses_credits={credits.paid_analyses_credits}
            />
          )}

          {/* User Menu */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">Mi Cuenta</span>
            <span className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-white font-semibold">
              {credits?.total_analyses_used.toString() || '0'}
            </span>
          </div>
        </nav>
      </div>
    </header>
  );
}
```

---

## ⚠️ Manejo de Errores

### 1. Error: 402 Payment Required

**Causa:** Usuario sin créditos.

**Acción:** Redirigir a `/pricing`.

**Código:**
```typescript
if (error.response?.status === 402) {
  router.push('/pricing');
}
```

### 2. Error: 401 Unauthorized

**Causa:** Token JWT expirado o inválido.

**Acción:** Redirigir a `/login` y limpiar token.

**Código:**
```typescript
if (error.response?.status === 401) {
  localStorage.removeItem('token');
  router.push('/login');
}
```

### 3. Error: 500 Server Error

**Causa:** Problema en el backend.

**Acción:** Mostrar mensaje amigable y ofrecer retry.

**Código:**
```typescript
if (error.response?.status === 500) {
  alert('Hubo un error en el servidor. Por favor intenta nuevamente.');
}
```

---

## 🧪 Pruebas y QA

### Casos de Prueba

| Caso | Pasos | Resultado Esperado |
|-------|--------|-------------------|
| Usuario nuevo ve créditos | Login → Verificar UI | Muestra "3 análisis disponibles" |
| Agotar análisis gratis | Hacer 3 análisis | Muestra "0 análisis disponibles" |
| Intentar análisis sin créditos | POST /analysis/submit sin créditos | 402 + redirección a pricing |
| Ver paquetes | GET /credit-packages | Muestra 3 paquetes |
| Comprar paquete | Click en "Comprar" → Pagar | Redirige a MercadoPago |
| Pago exitoso | MercadoPago callback | Créditos actualizados en UI |
| Token expirado | Usar API con token viejo | Redirige a login |

### Testing Local

1. **Mock del backend:**
   ```typescript
   // Mock para testing
   export const mockCreditsService = {
     async getCredits() {
       return {
         free_analyses_remaining: 0,
         paid_analyses_credits: 50,
         total_analyses_used: 3,
       };
     },
   };
   ```

2. **Testing del interceptor:**
   ```typescript
   // Mock de 402 response
   apiClient.interceptors.response.use(
     (response) => {
       if (response.config.url?.includes('/analysis/submit')) {
         return { ...response, status: 402, headers: { 'x-needs-payment': 'true' } };
       }
       return response;
     }
   );
   ```

3. **Manual testing:**
   - Usar tokens de MercadoPago sandbox
   - Simular callback de éxito con parámetros en URL
   - Verificar que se actualice el badge de créditos

---

## 📚 Referencias Adicionales

### MercadoPago Documentation
- [Checkout Pro](https://www.mercadopago.com.ar/developers/es/docs/checkout-pro/integration-configuration/integrate-checkout)
- [Webhooks](https://www.mercadopago.com.ar/developers/es/docs/checkout-pro/webhooks)

### Backend API
- Ver `doc/Backend-Functions.md` para endpoints completos
- OpenAPI/Swagger disponible en `http://localhost:8000/docs`

---

## ✅ Checklist de Implementación

- [ ] Crear `services/credits.service.ts`
- [ ] Crear `components/CreditBadge.tsx`
- [ ] Crear `components/PricingCard.tsx`
- [ ] Crear `components/PaymentInterceptor.ts` (o usar axios interceptor)
- [ ] Crear `app/pricing/page.tsx`
- [ ] Integrar CreditBadge en Header/Navbar
- [ ] Integrar interceptor de 402 en API client
- [ ] Agregar loading states en todas las llamadas
- [ ] Agregar manejo de errores con mensajes amigables
- [ ] Testear flujo completo con sandbox de MercadoPago
- [ ] Testear casos de error (402, 401, 500)
- [ ] Verificar actualización de créditos después del pago
- [ ] Testear en diferentes pantallas (desktop, mobile)
- [ ] Verificar accesibilidad (ARIA labels, keyboard navigation)

---

## 🎨 Sugerencias de UX/UI

1. **Badge siempre visible:** Colocar CreditBadge en header de todas las páginas
2. **Feedback visual:** Animación cuando se actualizan los créditos
3. **Estado de carga:** Skeletons mientras se cargan los créditos
4. **Modal de alerta:** Mensaje claro cuando no hay créditos
5. **Destacar mejor valor:** Marcar Pack 50 como "Más popular"
6. **Confianza:** Mostrar logos de MercadoPago y badges de seguridad
7. **Claridad:** Explicar "3 análisis gratis" al usuario nuevo

---

**Última actualización:** 2026-04-03

**Backend versión:** 0.1.0
