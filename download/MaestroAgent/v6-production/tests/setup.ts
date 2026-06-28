// Jest setup — runs before every test file
// Mocks external dependencies, sets up test env

import { config } from 'dotenv';

// Load test env
config({ path: '.env.test' });

// Set fallback test env vars if not set
process.env.NODE_ENV = process.env.NODE_ENV || 'test';
process.env.DATABASE_URL = process.env.DATABASE_URL || 'postgresql://postgres:postgres@localhost:5432/maestro_test';
process.env.REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
process.env.ENCRYPTION_KEY = process.env.ENCRYPTION_KEY || 'a'.repeat(64);
process.env.NEXTAUTH_URL = process.env.NEXTAUTH_URL || 'http://localhost:3000';
process.env.NEXTAUTH_SECRET = process.env.NEXTAUTH_SECRET || 'test-secret-at-least-32-characters-long';
process.env.LOG_LEVEL = process.env.LOG_LEVEL || 'error'; // Quiet in tests

// Mock Redis for unit tests (integration tests use real Redis)
jest.mock('ioredis', () => {
  const Redis = jest.fn().mockImplementation(() => ({
    get: jest.fn().mockResolvedValue(null),
    setex: jest.fn().mockResolvedValue('OK'),
    eval: jest.fn().mockResolvedValue([1, 9, 0]),
    publish: jest.fn().mockResolvedValue(1),
    subscribe: jest.fn().mockResolvedValue('OK'),
    on: jest.fn(),
    quit: jest.fn().mockResolvedValue('OK'),
    ping: jest.fn().mockResolvedValue('PONG'),
  }));
  return { __esModule: true, default: Redis, Redis };
});
