import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Platform, SafeAreaView, ScrollView, StyleSheet, View } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator, NativeStackScreenProps } from '@react-navigation/native-stack';
import { Appbar, Button, Card, List, Provider as PaperProvider, Snackbar, Text, TextInput } from 'react-native-paper';
import { Camera, CameraType } from 'expo-camera';
import * as Location from 'expo-location';
import * as FileSystem from 'expo-file-system';
import * as Device from 'expo-device';
import { Buffer } from 'buffer';
import { sha256 } from 'js-sha256';

if (typeof global.Buffer === 'undefined') {
  (global as unknown as { Buffer: typeof Buffer }).Buffer = Buffer;
}

interface UserProfile {
  id: string;
  email: string;
  name?: string | null;
  role: string;
}

interface TripSummary {
  id: string;
  start_time_utc: string;
  end_time_utc?: string | null;
  status: string;
  segments: Array<{ id: string; index: number; sha256?: string | null; file_size_bytes?: number | null }>;
}

interface AuthState {
  token: string | null;
  serverUrl: string;
  user?: UserProfile;
  deviceId?: string;
}

interface AuthContextValue extends AuthState {
  setAuth: (state: AuthState) => void;
}

const AuthContext = createContext<AuthContextValue>({ token: null, serverUrl: '', setAuth: () => undefined });

const Stack = createNativeStackNavigator();

const useAuth = () => useContext(AuthContext);

const API = {
  async request(path: string, options: RequestInit = {}, auth: AuthState): Promise<Response> {
    if (!auth.serverUrl) {
      throw new Error('Server URL not configured');
    }
    const baseHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (auth.token) {
      baseHeaders.Authorization = `Bearer ${auth.token}`;
    }
    const res = await fetch(`${auth.serverUrl}${path}`, {
      ...options,
      headers: {
        ...baseHeaders,
        ...(options.headers as Record<string, string> | undefined),
      },
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`Request failed (${res.status}): ${detail}`);
    }
    return res;
  },
};

type RootStackParamList = {
  Login: undefined;
  Recorder: undefined;
  History: undefined;
};

type LoginScreenProps = NativeStackScreenProps<RootStackParamList, 'Login'>;
type RecorderScreenProps = NativeStackScreenProps<RootStackParamList, 'Recorder'>;
type HistoryScreenProps = NativeStackScreenProps<RootStackParamList, 'History'>;

const LoginScreen: React.FC<LoginScreenProps> = ({ navigation }) => {
  const auth = useAuth();
  const [serverUrl, setServerUrl] = useState(auth.serverUrl || 'http://localhost:8000');
  const [email, setEmail] = useState('rider@example.com');
  const [password, setPassword] = useState('changeme');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const normalizedServer = serverUrl.replace(/\/$/, '');
      const response = await API.request(
        '/auth/token',
        {
          method: 'POST',
          body: JSON.stringify({ email, password, name: email.split('@')[0] }),
        },
        { ...auth, serverUrl: normalizedServer },
      );
      const tokenPayload = await response.json();
      const profileResponse = await API.request('/me', {}, { ...auth, serverUrl: normalizedServer, token: tokenPayload.access_token });
      const profile = await profileResponse.json();
      const newState: AuthState = {
        serverUrl: normalizedServer,
        token: tokenPayload.access_token,
        user: profile,
      };
      auth.setAuth(newState);
      navigation.reset({ index: 0, routes: [{ name: 'Recorder' }] });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }, [auth, email, navigation, password, serverUrl]);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.form}>
        <Text variant="titleLarge" style={styles.title}>BikeRecorder Login</Text>
        <TextInput label="Server URL" value={serverUrl} onChangeText={setServerUrl} autoCapitalize="none" style={styles.input} />
        <TextInput label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" style={styles.input} />
        <TextInput label="Password" value={password} onChangeText={setPassword} secureTextEntry style={styles.input} />
        <Button mode="contained" onPress={handleLogin} loading={loading} disabled={loading} style={styles.cta}>
          Sign In
        </Button>
      </View>
      <Snackbar visible={!!error} onDismiss={() => setError(null)}>{error}</Snackbar>
    </SafeAreaView>
  );
};

interface RecordingState {
  startedAt: Date | null;
  videoUri: string | null;
  locationSamples: Location.LocationObject[];
}

const RecorderScreen: React.FC<RecorderScreenProps> = ({ navigation }) => {
  const auth = useAuth();
  const cameraRef = useRef<Camera | null>(null);
  const [cameraPermission, requestCameraPermission] = Camera.useCameraPermissions();
  const [locationPermission, requestLocationPermission] = Location.useForegroundPermissions();
  const [recordingState, setRecordingState] = useState<RecordingState>({ startedAt: null, videoUri: null, locationSamples: [] });
  const [recordingPromise, setRecordingPromise] = useState<Promise<FileSystem.VideoRecording> | null>(null);
  const [locationSub, setLocationSub] = useState<Location.LocationSubscription | null>(null);
  const [timer, setTimer] = useState<number>(0);
  const [deviceId, setDeviceId] = useState<string | undefined>(auth.deviceId);
  const [uploading, setUploading] = useState(false);
  const [snackbar, setSnackbar] = useState<string | null>(null);

  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (recordingState.startedAt) {
      interval = setInterval(() => {
        if (recordingState.startedAt) {
          const diff = Math.floor((Date.now() - recordingState.startedAt.getTime()) / 1000);
          setTimer(diff);
        }
      }, 1000);
    } else {
      setTimer(0);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [recordingState.startedAt]);

  useEffect(() => {
    if (!cameraPermission) {
      requestCameraPermission();
    }
  }, [cameraPermission, requestCameraPermission]);

  useEffect(() => {
    if (!locationPermission) {
      requestLocationPermission();
    }
  }, [locationPermission, requestLocationPermission]);

  useEffect(() => () => {
    if (locationSub) {
      locationSub.remove();
    }
  }, [locationSub]);

  const ensureDeviceRegistration = useCallback(async () => {
    if (deviceId || !auth.token) {
      return;
    }
    const platform = Platform.OS === 'ios' ? 'ios' : 'android';
    const response = await API.request(
      '/devices/register',
      {
        method: 'POST',
        body: JSON.stringify({
          platform,
          model: Device.modelName ?? 'Unknown',
          os_version: Device.osVersion ?? 'Unknown',
          app_version: '0.1.0',
        }),
      },
      auth,
    );
    const device = await response.json();
    setDeviceId(device.id);
    auth.setAuth({ token: auth.token, serverUrl: auth.serverUrl, user: auth.user, deviceId: device.id });
  }, [auth, deviceId]);

  const handleStartRecording = useCallback(async () => {
    try {
      await ensureDeviceRegistration();
      if (!cameraPermission?.granted) {
        const status = await requestCameraPermission();
        if (!status.granted) {
          throw new Error('Camera permission denied');
        }
      }
      if (!locationPermission?.granted) {
        const status = await requestLocationPermission();
        if (!status.granted) {
          throw new Error('Location permission denied');
        }
      }
      const watch = await Location.watchPositionAsync(
        {
          accuracy: Location.Accuracy.BestForNavigation,
          timeInterval: 1000,
          distanceInterval: 0,
        },
        (sample) => {
          setRecordingState((prev) => ({ ...prev, locationSamples: [...prev.locationSamples, sample] }));
        },
      );
      setLocationSub(watch);
      const startedAt = new Date();
      setRecordingState({ startedAt, videoUri: null, locationSamples: [] });
      const promise = cameraRef.current?.recordAsync({ quality: Camera.Constants.VideoQuality['1080p'], maxDuration: 7200 });
      if (!promise) {
        throw new Error('Camera not ready');
      }
      setRecordingPromise(promise);
      setSnackbar('Recording started');
    } catch (err) {
      setSnackbar(err instanceof Error ? err.message : 'Unable to start recording');
    }
  }, [cameraPermission?.granted, ensureDeviceRegistration, locationPermission?.granted, requestCameraPermission, requestLocationPermission]);

  const handleStopRecording = useCallback(async () => {
    try {
      if (!recordingPromise) {
        return;
      }
      cameraRef.current?.stopRecording();
      const recording = await recordingPromise;
      if (locationSub) {
        locationSub.remove();
        setLocationSub(null);
      }
      setRecordingState((prev) => ({ ...prev, videoUri: recording.uri }));
      setRecordingPromise(null);
      setSnackbar('Recording saved. Preparing upload…');
      await uploadTrip(recording.uri);
    } catch (err) {
      setSnackbar(err instanceof Error ? err.message : 'Failed to finalize recording');
    }
  }, [locationSub, recordingPromise, uploadTrip]);

  const uploadTrip = useCallback(
    async (videoUri: string) => {
      if (!auth.token || !deviceId || !recordingState.startedAt) {
        setSnackbar('Missing recording context');
        return;
      }
      try {
        setUploading(true);
        const fileInfo = await FileSystem.getInfoAsync(videoUri, { size: true });
        if (!fileInfo.exists || !fileInfo.size) {
          throw new Error('Video file missing');
        }
        const startIso = recordingState.startedAt.toISOString();
        const endIso = new Date().toISOString();
        const tripResponse = await API.request(
          '/trips',
          {
            method: 'POST',
            body: JSON.stringify({
              device_id: deviceId,
              start_time_utc: startIso,
            }),
          },
          auth,
        );
        const trip = await tripResponse.json();
        const segmentResponse = await API.request(
          `/trips/${trip.id}/segments`,
          {
            method: 'POST',
            body: JSON.stringify({
              index: 0,
              video_codec: 'h264',
              expected_bytes: fileInfo.size,
              width: 1920,
              height: 1080,
              fps: 30,
            }),
          },
          auth,
        );
        const segment = await segmentResponse.json();
        const base64 = await FileSystem.readAsStringAsync(videoUri, { encoding: FileSystem.EncodingType.Base64 });
        const buffer = Buffer.from(base64, 'base64');
        const checksum = sha256(buffer);
        const uploadResponse = await API.request(
          '/uploads',
          {
            method: 'POST',
            body: JSON.stringify({
              trip_id: trip.id,
              segment_id: segment.id,
              filename: 'segment.mp4',
              file_type: 'video_mp4',
              sha256: checksum,
              upload_length: buffer.length,
            }),
          },
          auth,
        );
        const upload = await uploadResponse.json();
        const chunkSize = 5 * 1024 * 1024;
        let offset = 0;
        while (offset < buffer.length) {
          const nextChunk = buffer.subarray(offset, offset + chunkSize);
          await API.request(
            `/uploads/${upload.id}`,
            {
              method: 'PATCH',
              headers: {
                'Content-Type': 'application/offset+octet-stream',
                'Upload-Offset': String(offset),
              },
              body: nextChunk as any,
            },
            auth,
          );
          offset += nextChunk.length;
        }
        await API.request(
          `/trips/${trip.id}/segments/${segment.id}`,
          {
            method: 'PATCH',
            body: JSON.stringify({
              file_size_bytes: buffer.length,
              sha256: checksum,
              duration_s: timer,
              status: 'complete',
            }),
          },
          auth,
        );
        const metadataLines = recordingState.locationSamples.map((sample) =>
          JSON.stringify({
            ts: new Date(sample.timestamp ?? Date.now()).toISOString(),
            lat: sample.coords.latitude,
            lon: sample.coords.longitude,
            alt: sample.coords.altitude,
            spd: sample.coords.speed,
            brg: sample.coords.heading,
            acc: sample.coords.accuracy,
          }),
        );
        await API.request(
          `/segments/${segment.id}/metadata`,
          {
            method: 'POST',
            body: JSON.stringify({ type: 'gps_jsonl', content: metadataLines.join('\n'), filename: 'track.jsonl' }),
          },
          auth,
        );
        const duration = Math.max(
          timer,
          Math.floor((new Date(endIso).getTime() - recordingState.startedAt.getTime()) / 1000),
        );
        await API.request(
          `/trips/${trip.id}`,
          {
            method: 'PATCH',
            body: JSON.stringify({ end_time_utc: endIso, duration_s: duration, status: 'complete' }),
          },
          auth,
        );
        setRecordingState({ startedAt: null, videoUri: null, locationSamples: [] });
        setTimer(0);
        setSnackbar('Upload complete');
      } catch (err) {
        setSnackbar(err instanceof Error ? err.message : 'Upload failed');
      } finally {
        setUploading(false);
      }
    },
    [auth, deviceId, recordingState.locationSamples, recordingState.startedAt, timer],
  );

  const isRecording = !!recordingPromise;

  return (
    <SafeAreaView style={styles.container}>
      <Appbar.Header>
        <Appbar.Content title="Recorder" />
        <Appbar.Action icon="history" onPress={() => navigation.navigate('History')} />
      </Appbar.Header>
      <View style={styles.cameraContainer}>
        <Camera ref={(ref) => (cameraRef.current = ref)} style={styles.camera} type={CameraType.back} ratio="16:9" />
      </View>
      <View style={styles.hud}>
        <Text variant="titleLarge">{new Date(timer * 1000).toISOString().substring(11, 19)}</Text>
        <Text variant="bodyMedium">GPS samples: {recordingState.locationSamples.length}</Text>
      </View>
      <View style={styles.actions}>
        <Button mode="contained" icon={isRecording ? 'stop' : 'record'} onPress={isRecording ? handleStopRecording : handleStartRecording} disabled={uploading}>
          {isRecording ? 'Stop Recording' : 'Start Recording'}
        </Button>
      </View>
      <Snackbar visible={!!snackbar} onDismiss={() => setSnackbar(null)} duration={4000}>
        {snackbar}
      </Snackbar>
    </SafeAreaView>
  );
};

const HistoryScreen: React.FC<HistoryScreenProps> = ({ navigation }) => {
  const auth = useAuth();
  const [trips, setTrips] = useState<TripSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTrips = useCallback(async () => {
    if (!auth.token) {
      return;
    }
    try {
      setLoading(true);
      const res = await API.request('/trips', {}, auth);
      const payload = await res.json();
      setTrips(payload.trips ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trips');
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    const unsubscribe = navigation.addListener('focus', () => {
      loadTrips();
    });
    return unsubscribe;
  }, [loadTrips, navigation]);

  return (
    <SafeAreaView style={styles.container}>
      <Appbar.Header>
        <Appbar.BackAction onPress={() => navigation.goBack()} />
        <Appbar.Content title="Trip History" />
      </Appbar.Header>
      <ScrollView contentContainerStyle={styles.listContainer}>
        {loading ? (
          <Text style={styles.placeholder}>Loading…</Text>
        ) : trips.length === 0 ? (
          <Text style={styles.placeholder}>No trips yet</Text>
        ) : (
          trips.map((trip) => (
            <Card key={trip.id} style={styles.tripCard}>
              <Card.Title title={new Date(trip.start_time_utc).toLocaleString()} subtitle={`Status: ${trip.status}`} />
              <Card.Content>
                <Text>Segments: {trip.segments.length}</Text>
                {trip.segments.map((segment) => (
                  <List.Item
                    key={segment.id}
                    title={`Segment ${segment.index}`}
                    description={`Bytes: ${segment.file_size_bytes ?? 'n/a'} Hash: ${segment.sha256?.slice(0, 8) ?? 'n/a'}`}
                    left={(props) => <List.Icon {...props} icon="film" />}
                  />
                ))}
              </Card.Content>
            </Card>
          ))
        )}
      </ScrollView>
      <Snackbar visible={!!error} onDismiss={() => setError(null)}>{error}</Snackbar>
    </SafeAreaView>
  );
};

const App: React.FC = () => {
  const [authState, setAuthState] = useState<AuthState>({ token: null, serverUrl: '' });
  const contextValue = useMemo<AuthContextValue>(() => ({ ...authState, setAuth: setAuthState }), [authState]);
  return (
    <PaperProvider>
      <AuthContext.Provider value={contextValue}>
        <NavigationContainer>
          <Stack.Navigator initialRouteName={authState.token ? 'Recorder' : 'Login'}>
            <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
            <Stack.Screen name="Recorder" component={RecorderScreen} options={{ headerShown: false }} />
            <Stack.Screen name="History" component={HistoryScreen} options={{ headerShown: false }} />
          </Stack.Navigator>
        </NavigationContainer>
      </AuthContext.Provider>
    </PaperProvider>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f2f2f2',
  },
  form: {
    flex: 1,
    padding: 16,
    justifyContent: 'center',
  },
  title: {
    textAlign: 'center',
    marginBottom: 24,
  },
  input: {
    marginVertical: 8,
  },
  cta: {
    marginTop: 16,
  },
  cameraContainer: {
    flex: 3,
    backgroundColor: 'black',
  },
  camera: {
    flex: 1,
  },
  hud: {
    padding: 16,
    alignItems: 'center',
    backgroundColor: '#ffffff',
  },
  actions: {
    padding: 16,
    backgroundColor: '#ffffff',
  },
  listContainer: {
    padding: 16,
    gap: 12,
  },
  tripCard: {
    marginBottom: 12,
  },
  placeholder: {
    textAlign: 'center',
    marginTop: 24,
  },
});

export default App;
