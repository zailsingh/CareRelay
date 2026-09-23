import { PropsWithChildren, createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { api, CareProfile } from '@/lib/api';
import { deviceTimezone } from '@/lib/dates';
import { useAuth } from '@/providers/AuthProvider';

type CareProfileContextValue = {
  profiles: CareProfile[];
  activeProfile: CareProfile | null;
  loading: boolean;
  error: string | null;
  wellbeingRevision: number;
  careEventRevision: number;
  setActiveProfileId: (id: string) => void;
  createProfile: (name: string, forSelf?: boolean) => Promise<CareProfile | null>;
  refreshProfiles: () => Promise<void>;
  notifyWellbeingChanged: () => void;
  notifyCareEventChanged: () => void;
};

const CareProfileContext = createContext<CareProfileContextValue | null>(null);

export function CareProfileProvider({ children }: PropsWithChildren) {
  const { token } = useAuth();
  const [profiles, setProfiles] = useState<CareProfile[]>([]);
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [wellbeingRevision, setWellbeingRevision] = useState(0);
  const [careEventRevision, setCareEventRevision] = useState(0);

  const refreshProfiles = useCallback(async () => {
    if (!token) {
      setProfiles([]);
      setActiveProfileId(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const result = await api.profiles(token);
      setProfiles(result);
      setActiveProfileId((current) =>
        current && result.some((profile) => profile.id === current)
          ? current
          : result[0]?.id ?? null,
      );
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load care profiles.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { void refreshProfiles(); }, [refreshProfiles]);

  const createProfile = useCallback(async (name: string, forSelf = false) => {
    if (!token) return null;
    const created = await api.createProfile(token, name, deviceTimezone(), forSelf);
    setProfiles((current) => [created, ...current]);
    setActiveProfileId(created.id);
    return created;
  }, [token]);

  const activeProfile = profiles.find((profile) => profile.id === activeProfileId) ?? null;
  const value = useMemo(() => ({
    profiles,
    activeProfile,
    loading,
    error,
    wellbeingRevision,
    careEventRevision,
    setActiveProfileId,
    createProfile,
    refreshProfiles,
    notifyWellbeingChanged: () => setWellbeingRevision((current) => current + 1),
    notifyCareEventChanged: () => setCareEventRevision((current) => current + 1),
  }), [profiles, activeProfile, loading, error, wellbeingRevision, careEventRevision, createProfile, refreshProfiles]);

  return <CareProfileContext.Provider value={value}>{children}</CareProfileContext.Provider>;
}

export function useCareProfiles(): CareProfileContextValue {
  const value = useContext(CareProfileContext);
  if (!value) throw new Error('useCareProfiles must be used inside CareProfileProvider');
  return value;
}
