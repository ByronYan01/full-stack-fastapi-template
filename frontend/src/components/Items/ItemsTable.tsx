import { keepPreviousData, useQuery } from "@tanstack/react-query"
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table"
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Search,
} from "lucide-react"
import { useMemo, useState } from "react"

import type { ItemPublic } from "@/client"
import { ItemsService } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useDebounce } from "@/hooks/useDebounce"
import { columns as defaultColumns } from "./columns"

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]
const DEBOUNCE_MS = 300

type ItemsOrder = "asc" | "desc"

interface ItemsTableProps {
  /**
   * Optional column overrides. Defaults to the shared `columns` definition,
   * which includes the new `created_at` column.
   */
  columns?: ColumnDef<ItemPublic>[]
}

export function ItemsTable({ columns = defaultColumns }: ItemsTableProps) {
  const [q, setQ] = useState("")
  const debouncedQ = useDebounce(q, DEBOUNCE_MS)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZE_OPTIONS[0])
  const [order, setOrder] = useState<ItemsOrder>("desc")

  // NOTE: resetting `page` to 1 lives in the change handlers (not in a
  // `useEffect`) on purpose. React's "reset state on event, not on effect"
  // guidance applies here, and it also avoids biome's exhaustive-deps
  // collapsing the dependency array to `[]`. We reset on `q` (not on
  // `debouncedQ`) because React batches repeated `setPage(1)` calls, so the
  // user does not get yanked on every keystroke — the request simply fires
  // once `debouncedQ` settles.
  const onSearchChange = (value: string) => {
    setQ(value)
    setPage(1)
  }
  const onPageSizeChange = (next: number) => {
    setPageSize(next)
    setPage(1)
  }
  const toggleOrder = () => {
    setOrder((prev) => (prev === "desc" ? "asc" : "desc"))
    setPage(1)
  }

  const { data, isFetching, isError, error } = useQuery({
    queryKey: ["items", { debouncedQ, page, pageSize, order }],
    queryFn: () =>
      ItemsService.readItems({
        skip: (page - 1) * pageSize,
        limit: pageSize,
        title: debouncedQ.trim() || undefined,
        order,
      }),
    placeholderData: keepPreviousData,
  })

  const items = data?.data ?? []
  const count = data?.count ?? 0
  const totalPages = Math.max(1, Math.ceil(count / pageSize))
  // Clamp page when the result set shrinks below the current page (e.g. after
  // deletions). This keeps the right-side "Page X of Y" and the navigation
  // buttons truthful.
  const currentPage = Math.min(page, totalPages)

  const table = useReactTable({
    data: items,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    pageCount: totalPages,
  })

  const isFirstLoad = data === undefined
  const isEmpty = items.length === 0
  const hasSearch = debouncedQ.trim().length > 0

  // Memoize the message shown in the toolbar's order button so that the JSX
  // stays readable.
  const orderMeta = useMemo(
    () =>
      order === "desc"
        ? { label: "Newest", Icon: ArrowDown }
        : { label: "Oldest", Icon: ArrowUp },
    [order],
  )

  return (
    <div className="flex flex-col gap-4">
      {/* Toolbar: search + order toggle */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search className="text-muted-foreground absolute left-2.5 top-1/2 size-4 -translate-y-1/2" />
          <Input
            value={q}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search by title..."
            className="pl-8"
            aria-label="Search items by title"
          />
        </div>
        <Button
          variant="outline"
          onClick={toggleOrder}
          className="shrink-0"
          aria-label={`Sort by created date (${orderMeta.label.toLowerCase()} first)`}
        >
          <orderMeta.Icon className="size-4" />
          {orderMeta.label}
        </Button>
      </div>

      {/* Table area */}
      <div
        className={
          isFetching
            ? "relative transition-opacity duration-150 opacity-60 pointer-events-none"
            : "relative transition-opacity duration-150"
        }
      >
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id} className="hover:bg-transparent">
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {isFirstLoad ? (
              // Skeleton rows on the very first load — keeps the layout stable
              // and avoids the flash of an empty table.
              Array.from({ length: 3 }).map((_, rowIndex) => (
                <TableRow
                  key={`skeleton-${rowIndex}`}
                  className="hover:bg-transparent"
                >
                  {columns.map((_col, colIndex) => (
                    <TableCell key={`skeleton-${rowIndex}-${colIndex}`}>
                      <Skeleton className="h-5 w-full" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : isEmpty ? (
              <TableRow className="hover:bg-transparent">
                <TableCell
                  colSpan={columns.length}
                  className="h-32 text-center text-muted-foreground"
                >
                  {hasSearch ? (
                    <div className="flex flex-col items-center gap-1">
                      <span className="font-medium">
                        No items match &quot;{debouncedQ}&quot;
                      </span>
                      <span className="text-sm">Try a different keyword.</span>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-1">
                      <span className="font-medium">
                        You don&apos;t have any items yet
                      </span>
                      <span className="text-sm">
                        Add a new item to get started.
                      </span>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {isError && (
        <p className="text-sm text-destructive">
          Failed to load items:{" "}
          {error instanceof Error ? error.message : "Unknown error"}
        </p>
      )}

      {/* Pagination toolbar — always visible (per design decision D8.4). */}
      <div className="flex flex-col gap-4 border-t bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div className="text-sm text-muted-foreground">
            Total <span className="font-medium text-foreground">{count}</span>{" "}
            items
          </div>
          <div className="flex items-center gap-x-2">
            <p className="text-sm text-muted-foreground">Rows per page</p>
            <Select
              value={`${pageSize}`}
              onValueChange={(value) => onPageSizeChange(Number(value))}
            >
              <SelectTrigger className="h-8 w-[70px]">
                <SelectValue placeholder={pageSize} />
              </SelectTrigger>
              <SelectContent side="top">
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <SelectItem key={size} value={`${size}`}>
                    {size}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex items-center gap-x-6">
          <div className="flex items-center gap-x-1 text-sm text-muted-foreground">
            <span>Page</span>
            <span className="font-medium text-foreground">{currentPage}</span>
            <span>of</span>
            <span className="font-medium text-foreground">{totalPages}</span>
          </div>

          <div className="flex items-center gap-x-1">
            <Button
              variant="outline"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => setPage(1)}
              disabled={currentPage <= 1}
            >
              <span className="sr-only">Go to first page</span>
              <ChevronsLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1}
            >
              <span className="sr-only">Go to previous page</span>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages}
            >
              <span className="sr-only">Go to next page</span>
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => setPage(totalPages)}
              disabled={currentPage >= totalPages}
            >
              <span className="sr-only">Go to last page</span>
              <ChevronsRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
