import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { location, renderWithProviders } from '@/test/render'
import { fixtures, server } from '@/test/server'
import { UploadsPage } from './UploadsPage'

const csv = (name = 'week1.csv', body = 'Game,Off,Def,Play Type\nG1,DET,GB,pass\n') => new File([body], name, { type: 'text/csv' })

describe('UploadsPage', () => {
  it('lists your uploads with their status', async () => {
    renderWithProviders(<UploadsPage />, { route: '/uploads' })
    const link = await screen.findByRole('link', { name: fixtures.uploadReady.name })
    expect(link).toHaveAttribute('href', `/uploads/${fixtures.uploadReady.id}`)
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByText('2,245 plays')).toBeInTheDocument()
  })

  it('shows an empty state with guidance when there are no uploads', async () => {
    server.use(http.get('*/api/v1/uploads', () => HttpResponse.json({ items: [], page: 1, page_size: 50, total: 0 })))
    renderWithProviders(<UploadsPage />, { route: '/uploads' })
    expect(await screen.findByText('No uploads yet')).toBeInTheDocument()
  })

  it('rejects the wrong file type and oversized files before uploading', async () => {
    const user = userEvent.setup({ applyAccept: false })
    let posted = 0
    server.use(http.post('*/api/v1/uploads', () => {
      posted += 1
      return HttpResponse.json(fixtures.uploadUploaded, { status: 201 })
    }))
    renderWithProviders(<UploadsPage />, { route: '/uploads' })
    const input = screen.getByTestId('file-input')

    await user.upload(input, new File(['%PDF'], 'playbook.pdf', { type: 'application/pdf' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose a CSV file')
    expect(screen.getByRole('button', { name: 'Upload and check' })).toBeDisabled()

    const big = csv('season.csv')
    Object.defineProperty(big, 'size', { value: 26 * 1024 * 1024 })
    await user.upload(input, big)
    expect(await screen.findByRole('alert')).toHaveTextContent('at most 25 MB')

    await user.upload(input, csv('empty.csv', ''))
    expect(await screen.findByRole('alert')).toHaveTextContent('This file is empty')
    expect(posted).toBe(0)
  })

  it('uploads a CSV with a name and opens it for mapping', async () => {
    const user = userEvent.setup()
    let form: FormData | null = null
    server.use(
      http.post('*/api/v1/uploads', async ({ request }) => {
        form = await request.formData()
        return HttpResponse.json(fixtures.uploadUploaded, { status: 201 })
      }),
    )
    renderWithProviders(<UploadsPage />, { route: '/uploads' })
    await user.upload(screen.getByTestId('file-input'), csv())
    expect(screen.getByLabelText('Name')).toHaveValue('week1')
    await user.clear(screen.getByLabelText('Name'))
    await user.type(screen.getByLabelText('Name'), 'Week 1 charting')
    await user.click(screen.getByRole('button', { name: 'Upload and check' }))

    await waitFor(() => expect(location.current).toBe(`/uploads/${fixtures.uploadUploaded.id}`))
    const sent = form as unknown as FormData
    expect(sent.get('name')).toBe('Week 1 charting')
    expect(sent.get('file')).toHaveProperty('size', 38)
  })

  it('explains server-side rejections and links to a duplicate', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/api/v1/uploads', () =>
        HttpResponse.json(
          {
            error: {
              code: 'duplicate_upload',
              message: 'You already uploaded this file',
              request_id: 'd',
              details: { existing_upload_id: fixtures.uploadReady.id },
            },
          },
          { status: 409 },
        ),
      ),
    )
    renderWithProviders(<UploadsPage />, { route: '/uploads' })
    await user.upload(screen.getByTestId('file-input'), csv())
    await user.click(screen.getByRole('button', { name: 'Upload and check' }))
    expect(await screen.findByText(/You already uploaded this file/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open the existing upload' })).toHaveAttribute(
      'href',
      `/uploads/${fixtures.uploadReady.id}`,
    )
  })
})
