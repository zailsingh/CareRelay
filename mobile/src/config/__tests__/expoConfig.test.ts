import appConfig from '../../../app.json';

describe('Expo configuration', () => {
  it('configures native Sign in with Apple for the CareRelay bundle', () => {
    expect(appConfig.expo.ios.bundleIdentifier).toBe('com.carerelay.mobile');
    expect(appConfig.expo.ios.usesAppleSignIn).toBe(true);
    expect(appConfig.expo.plugins).toContain('expo-apple-authentication');
  });

  it('uses the supported SDK 57 scene lifecycle opt-in for Xcode 27', () => {
    const scenePlugin = appConfig.expo.plugins.find(
      (plugin): plugin is [string, { ios: { enableSceneSupport: boolean } }] => Array.isArray(plugin) && plugin[0] === 'expo-build-properties',
    );

    expect(scenePlugin?.[1].ios.enableSceneSupport).toBe(true);
    expect(appConfig.expo.ios).not.toHaveProperty('infoPlist.UIApplicationSceneManifest');
  });
});
