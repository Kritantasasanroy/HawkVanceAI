import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from './schema.js';

export type DrizzleDatabase = ReturnType<typeof drizzle<typeof schema>>;

export class Database {
  readonly drizzle: DrizzleDatabase;
  private readonly connection: postgres.Sql;

  private constructor(connection: postgres.Sql, orm: DrizzleDatabase) {
    this.connection = connection;
    this.drizzle = orm;
  }

  static connect(databaseUrl: string, maxConnections = 10): Database {
    const connection = postgres(databaseUrl, { max: maxConnections, onnotice: () => undefined });
    return new Database(connection, drizzle(connection, { schema }));
  }

  async isReachable(): Promise<boolean> {
    const probe = await this.connection`select 1 as ok`;
    return probe.length === 1;
  }

  async close(): Promise<void> {
    await this.connection.end({ timeout: 5 });
  }
}
