# Room discovers entities and DAOs through annotations/generated code.
-keep class **.data.local.** { *; }
-keep @androidx.room.Entity class * { *; }
-keep @androidx.room.Dao class * { *; }

# SQLCipher loads native symbols from its packaged AAR.
-keep class net.zetetic.database.sqlcipher.** { *; }

# Kotlin serialization-generated serializers are referenced reflectively.
-keepclassmembers class **$$serializer { *; }
-keepclassmembers class **$Companion { *; }

# Never log or retain tokens; this is a reminder for future rules and reviews.
