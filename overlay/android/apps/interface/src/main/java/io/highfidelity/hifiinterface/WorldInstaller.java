//
//  WorldInstaller.java
//  android/apps/interface/src/main/java/io/highfidelity/hifiinterface
//
//  Overlay file for the native Vircadia Android build. Not part of the
//  upstream tree; added by scripts/apply-overlay.sh.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
//  Copies the world pack shipped in the APK's assets into the app's private
//  files directory and rewrites @WORLD_ROOT@ to that real path, so the engine
//  can open the world with a plain file:/// address and load every model
//  locally. Runs off the UI thread.
//
//  Uses only plain Android SDK APIs that are available at minSdk 24.
//

package io.highfidelity.hifiinterface;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.util.Log;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.Charset;

public final class WorldInstaller {

    private static final String TAG = "Interface";

    /** Directory under the APK assets holding the generated world pack. */
    private static final String ASSET_ROOT = "world";
    /** Directory created under getFilesDir(). */
    public static final String WORLD_DIR = "world";
    /** The world description produced by scripts/build_world.py. */
    public static final String WORLD_JSON = "daybreak.json";
    /** Written last, so its presence means a complete install. */
    private static final String MARKER = ".installed";
    /** Placeholder substituted with the real install path. */
    private static final String WORLD_ROOT_TOKEN = "@WORLD_ROOT@";

    private static final Charset UTF8 = Charset.forName("UTF-8");
    private static final int BUFFER = 32 * 1024;

    private WorldInstaller() {
    }

    /** The world JSON the client should boot into, once installed. */
    public static File installedWorldJson(Context context) {
        return new File(new File(context.getFilesDir(), WORLD_DIR), WORLD_JSON);
    }

    /**
     * Install the world pack on a background thread. Safe to call on every
     * launch: a version marker short-circuits the work when the pack is current.
     *
     * Deliberately asynchronous. The pack can contain tens of megabytes, so
     * doing this inline would block onCreate and risk an ANR, and the first
     * launch therefore boots to the engine's own default world rather than to
     * Daybreak. The second launch onwards gets Daybreak. Documented in
     * LIMITATIONS.md.
     */
    public static void installAsync(final Context context) {
        Thread worker = new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    boolean installed = install(context);
                    Log.d(TAG, installed ? "world pack installed" : "world pack already current");
                } catch (IOException e) {
                    Log.w(TAG, "world pack install failed: " + e);
                } catch (RuntimeException e) {
                    Log.w(TAG, "world pack install failed: " + e);
                }
            }
        }, "WorldInstaller");
        worker.setDaemon(true);
        worker.start();
    }

    /**
     * @return true if files were written, false if the installed pack was
     *         already current.
     */
    public static boolean install(Context context) throws IOException {
        File target = new File(context.getFilesDir(), WORLD_DIR);
        File marker = new File(target, MARKER);
        String stamp = assetStamp(context);

        if (marker.isFile()) {
            String installed = readAll(new FileInputStream(marker)).trim();
            if (stamp.equals(installed)) {
                return false;
            }
            Log.d(TAG, "world pack stale (" + installed + " -> " + stamp + "), reinstalling");
        }

        copyAssetTree(context, ASSET_ROOT, target);

        File json = new File(target, WORLD_JSON);
        if (json.isFile()) {
            String text = readAll(new FileInputStream(json));
            if (text.indexOf(WORLD_ROOT_TOKEN) >= 0) {
                writeAll(json, text.replace(WORLD_ROOT_TOKEN, target.getAbsolutePath()));
                Log.d(TAG, "rewrote " + WORLD_ROOT_TOKEN + " -> " + target.getAbsolutePath());
            }
        } else {
            Log.w(TAG, "no " + WORLD_JSON + " in the world pack; nothing to boot into");
        }

        // Written last: its presence means a complete install.
        writeAll(marker, stamp);
        return true;
    }

    /**
     * A value that changes whenever the installed APK changes, so a reinstall
     * or an update triggers a refresh without needing a manual wipe.
     */
    private static String assetStamp(Context context) {
        try {
            PackageInfo info = context.getPackageManager()
                    .getPackageInfo(context.getPackageName(), 0);
            return info.versionCode + ":" + info.lastUpdateTime;
        } catch (Exception e) {
            return "0:0";
        }
    }

    private static void copyAssetTree(Context context, String assetPath, File targetDir)
            throws IOException {
        String[] children = context.getAssets().list(assetPath);
        if (children == null || children.length == 0) {
            // A leaf: copy it.
            if (!targetDir.getParentFile().exists() && !targetDir.getParentFile().mkdirs()) {
                throw new IOException("cannot create " + targetDir.getParentFile());
            }
            InputStream in = context.getAssets().open(assetPath);
            try {
                copy(in, targetDir);
            } finally {
                in.close();
            }
            return;
        }
        if (!targetDir.exists() && !targetDir.mkdirs()) {
            throw new IOException("cannot create " + targetDir);
        }
        for (String child : children) {
            String childAsset = assetPath + "/" + child;
            copyAssetTree(context, childAsset, new File(targetDir, child));
        }
    }

    private static void copy(InputStream in, File out) throws IOException {
        OutputStream os = new FileOutputStream(out);
        try {
            byte[] buffer = new byte[BUFFER];
            int read;
            while ((read = in.read(buffer)) > 0) {
                os.write(buffer, 0, read);
            }
        } finally {
            os.close();
        }
    }

    private static String readAll(InputStream in) throws IOException {
        BufferedReader reader = new BufferedReader(new InputStreamReader(in, UTF8));
        try {
            StringBuilder out = new StringBuilder();
            char[] buffer = new char[BUFFER];
            int read;
            while ((read = reader.read(buffer)) > 0) {
                out.append(buffer, 0, read);
            }
            return out.toString();
        } finally {
            reader.close();
        }
    }

    private static void writeAll(File file, String text) throws IOException {
        File parent = file.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new IOException("cannot create " + parent);
        }
        Writer writer = new OutputStreamWriter(new FileOutputStream(file), UTF8);
        try {
            writer.write(text);
        } finally {
            writer.close();
        }
    }
}
